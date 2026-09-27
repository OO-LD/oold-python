"""The bundled LangChain adapter.

No provider is called. The tests check what the adapter sends and what it
reads back, because both have already been wrong in a way that looked like a
model failing.
"""

import pytest

from oold.agent.client import Message

pytest.importorskip("langchain_core")

from oold.agent.langchain_client import (
    LangChainClient,
    fold_system_into_user,
    usage_from_message,
)


class _Reply:
    def __init__(self, content: str, usage: dict | None = None) -> None:
        self.content = content
        self.usage_metadata = usage


class _Recorder:
    """A chat model that records the turns it was handed."""

    def __init__(self, content: str = "ok", usage: dict | None = None) -> None:
        self.content = content
        self.usage = usage
        self.seen: list[tuple[str, str]] = []

    def invoke(self, turns):
        self.seen = list(turns)
        return _Reply(self.content, self.usage)


class TestReadingTokenCounts:
    def test_counts_are_read_off_the_message(self):
        usage = usage_from_message(_Reply("x", {"input_tokens": 12, "output_tokens": 3}))
        assert usage.input_tokens == 12
        assert usage.output_tokens == 3

    def test_a_provider_reporting_nothing_yields_zeros(self):
        """A zero total means the provider sent no token counts."""
        assert usage_from_message(_Reply("x")).total == 0

    def test_cached_and_reasoning_details_are_read_when_present(self):
        usage = usage_from_message(
            _Reply(
                "x",
                {
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "input_token_details": {"cache_read": 80},
                    "output_token_details": {"reasoning": 7},
                },
            )
        )
        assert usage.cached_input_tokens == 80
        assert usage.reasoning_tokens == 7


class TestFoldingTheSystemMessage:
    """Some deployments accept a system message and silently drop it."""

    def test_folding_puts_the_system_content_in_the_first_user_turn(self):
        turns = fold_system_into_user([
            Message(role="system", content="Answer in JSON."),
            Message(role="user", content="The reading was 40.1 hertz."),
        ])
        assert len(turns) == 1
        assert turns[0][0] == "user"
        assert "Answer in JSON." in turns[0][1]
        assert "40.1 hertz" in turns[0][1]

    def test_nothing_is_lost_when_there_is_no_system_message(self):
        assert fold_system_into_user([Message(role="user", content="Hello.")]) == [("user", "Hello.")]

    def test_a_system_message_with_nothing_to_fold_into_is_left_alone(self):
        assert fold_system_into_user([Message(role="system", content="Only this.")]) == [("system", "Only this.")]

    def test_later_turns_are_untouched(self):
        turns = fold_system_into_user([
            Message(role="system", content="S"),
            Message(role="user", content="A"),
            Message(role="assistant", content="B"),
            Message(role="user", content="C"),
        ])
        assert turns[1:] == [("assistant", "B"), ("user", "C")]

    def test_the_client_does_not_fold_unless_asked(self):
        """Folding changes the prompt, so it is declared and not guessed."""
        llm = _Recorder()
        LangChainClient(llm, model="m").invoke([
            Message(role="system", content="S"),
            Message(role="user", content="U"),
        ])
        assert [role for role, _ in llm.seen] == ["system", "user"]

    def test_the_client_folds_when_asked(self):
        llm = _Recorder()
        LangChainClient(llm, model="m", fold_system=True).invoke([
            Message(role="system", content="S"),
            Message(role="user", content="U"),
        ])
        assert [role for role, _ in llm.seen] == ["user"]
        assert llm.seen[0][1] == "S\n\nU"

    def test_folding_is_visible_on_the_client(self):
        assert LangChainClient(_Recorder(), model="m", fold_system=True).fold_system is True
        assert LangChainClient(_Recorder(), model="m").fold_system is False
