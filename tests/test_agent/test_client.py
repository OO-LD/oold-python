"""The model boundary and per-call token attribution."""

import threading

import pytest

from oold.agent import Call, CallLog, ChatClient, ChatResponse, Message, TokenUsage


class FakeClient:
    """A ChatClient that never talks to anything."""

    model = "fake-1"

    def __init__(self, usage: TokenUsage | None = None) -> None:
        self.usage = usage or TokenUsage(input_tokens=100, output_tokens=10)
        self.calls: list[tuple[Message, ...]] = []

    def invoke(self, messages, *, response_format=None) -> ChatResponse:
        self.calls.append(tuple(messages))
        return ChatResponse(text="ok", parsed=None, usage=self.usage)


class TestTokenUsage:
    def test_cached_input_is_inside_input_not_added_to_it(self):
        usage = TokenUsage(input_tokens=1000, cached_input_tokens=900)
        assert usage.total == 1000
        assert usage.billable_input == 100

    def test_usage_adds(self):
        total = TokenUsage(input_tokens=10, output_tokens=1) + TokenUsage(
            input_tokens=20, output_tokens=2, cached_input_tokens=5
        )
        assert total.input_tokens == 30
        assert total.output_tokens == 3
        assert total.cached_input_tokens == 5

    def test_an_uninstrumented_client_reports_zero_rather_than_guessing(self):
        assert TokenUsage().total == 0

    def test_describe_carries_every_tier(self):
        described = TokenUsage(1, 2, 3, 4).describe()
        assert set(described) == {
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "total_tokens",
        }


class TestCallLog:
    def test_totals_sum_every_call(self):
        log = CallLog()
        for step in ("detect", "extract", "construct"):
            log.append(
                Call(
                    step=step,
                    model="m",
                    usage=TokenUsage(input_tokens=100, output_tokens=5),
                    elapsed_s=0.1,
                )
            )
        assert len(log) == 3
        assert log.totals().input_tokens == 300

    def test_by_step_separates_what_the_run_total_hides(self):
        log = CallLog()
        log.append(Call("detect", "m", TokenUsage(input_tokens=8000), 0.1))
        log.append(Call("extract", "m", TokenUsage(input_tokens=500), 0.1))
        by_step = log.by_step()
        assert by_step["detect"].input_tokens == 8000
        assert by_step["extract"].input_tokens == 500

    def test_timed_records_the_usage_put_into_the_sink(self):
        log = CallLog()
        with log.timed("detect", "m", schema_sha256="abc") as sink:
            sink.append(TokenUsage(input_tokens=42))
        call = next(iter(log))
        assert call.usage.input_tokens == 42
        assert call.schema_sha256 == "abc"
        assert call.error is None
        assert call.elapsed_s >= 0

    def test_a_failed_call_still_leaves_a_record(self):
        """A retry that vanishes from the log makes retries look free."""
        log = CallLog()
        with pytest.raises(RuntimeError), log.timed("extract", "m"):
            raise RuntimeError("provider said no")
        call = next(iter(log))
        assert call.error == "RuntimeError: provider said no"
        assert call.usage.total == 0

    def test_attempts_are_recorded_separately(self):
        log = CallLog()
        for attempt in (1, 2, 3):
            log.append(Call("construct", "m", TokenUsage(input_tokens=10), 0.1, attempt))
        assert [c.attempt for c in log] == [1, 2, 3]
        assert log.totals().input_tokens == 30

    def test_appends_from_several_threads_all_arrive(self):
        """Some orchestrations fan out; a lost append is a silent undercount."""
        log = CallLog()

        def work():
            for _ in range(50):
                log.append(Call("parallel", "m", TokenUsage(input_tokens=1), 0.0))

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(log) == 400
        assert log.totals().input_tokens == 400

    def test_describe_counts_errors(self):
        log = CallLog()
        log.append(Call("a", "m", TokenUsage(), 0.1))
        log.append(Call("b", "m", TokenUsage(), 0.1, error="boom"))
        described = log.describe()
        assert described["n_calls"] == 2
        assert described["n_errors"] == 1
        assert set(described["by_step"]) == {"a", "b"}


class TestProtocol:
    def test_a_plain_object_satisfies_the_protocol(self):
        assert isinstance(FakeClient(), ChatClient)

    def test_the_agent_needs_no_sdk_to_be_exercised(self):
        client = FakeClient()
        reply = client.invoke([Message(role="user", content="hello")])
        assert reply.text == "ok"
        assert reply.usage.input_tokens == 100


class TestLangChainAdapter:
    def test_usage_is_read_off_a_langchain_message(self):
        adapter = pytest.importorskip(
            "oold.agent.langchain_client",
            reason="the agent extra is not installed",
        )

        class Reply:
            usage_metadata = {
                "input_tokens": 1200,
                "output_tokens": 80,
                "input_token_details": {"cache_read": 1000},
                "output_token_details": {"reasoning": 40},
            }

        usage = adapter.usage_from_message(Reply())
        assert usage.input_tokens == 1200
        assert usage.cached_input_tokens == 1000
        assert usage.reasoning_tokens == 40
        assert usage.billable_input == 200

    def test_a_provider_reporting_nothing_yields_zeros(self):
        adapter = pytest.importorskip(
            "oold.agent.langchain_client",
            reason="the agent extra is not installed",
        )
        assert adapter.usage_from_message(object()).total == 0

    def test_missing_detail_dictionaries_do_not_raise(self):
        adapter = pytest.importorskip(
            "oold.agent.langchain_client",
            reason="the agent extra is not installed",
        )

        class Reply:
            usage_metadata = {"input_tokens": 10, "output_tokens": 2}

        usage = adapter.usage_from_message(Reply())
        assert usage.total == 12
        assert usage.cached_input_tokens == 0
