"""Running an extraction under each condition, with no model involved.

The fake client records what it was sent and returns what the test tells it
to, so every assertion here is about the agent and nothing else.
"""

import json

import pytest

from oold.agent import (
    ARMS,
    ChatResponse,
    DecodeConstraint,
    Enforcement,
    ExtractionAgent,
    ExtractionRequest,
    Orchestration,
    OutputForm,
    TokenUsage,
    arm,
    build_messages,
    parse_json_answer,
    profile_for,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "value": {"type": "number"},
        "unit": {"type": "string"},
    },
    "required": ["type", "value"],
}

CATALOGUE = ("quantities.Length", "quantities.Mass")


class FakeClient:
    model = "fake-1"

    def __init__(self, text: str = '{"type": "quantities.Length", "value": 1.0}'):
        self.text = text
        self.messages = None
        self.response_format = None
        self.calls = 0

    def invoke(self, messages, *, response_format=None):
        self.calls += 1
        self.messages = list(messages)
        self.response_format = response_format
        return ChatResponse(
            text=self.text,
            parsed=None,
            usage=TokenUsage(input_tokens=100, output_tokens=10),
        )

    def system(self) -> str:
        return self.messages[0].content if self.messages else ""


def agent(name: str, client: FakeClient, profile: str = "openai", **kwargs):
    """An agent for one arm. A0 offers no catalogue, so it is not given one."""
    condition = ARMS[name] if ARMS[name].catalogue is None else arm(name, CATALOGUE)
    return ExtractionAgent(client, condition, profile_for(profile), **kwargs)


class TestThePromptFollowsTheCondition:
    def test_a0_is_shown_no_schema_and_no_catalogue(self):
        client = FakeClient()
        agent("A0-json", client).run(ExtractionRequest("doc", SCHEMA))
        system = client.system()
        assert "schema" not in system.lower()
        assert "quantities.Length" not in system

    def test_a1_is_shown_the_catalogue_and_the_schema(self):
        client = FakeClient()
        agent("A1", client).run(ExtractionRequest("doc", SCHEMA))
        system = client.system()
        assert "quantities.Length" in system
        assert "conform to this schema" in system

    def test_the_document_is_the_user_message_and_nothing_else(self):
        client = FakeClient()
        agent("A2", client).run(ExtractionRequest("the document text", SCHEMA))
        assert client.messages[1].content == "the document text"

    def test_the_shared_instruction_is_identical_across_arms(self):
        """Any wording difference between arms would be a confound."""
        firsts = set()
        for name in ("A0-json", "A1", "A2", "A3"):
            client = FakeClient()
            agent(name, client).run(ExtractionRequest("doc", SCHEMA))
            firsts.add(client.system().split("\n\n")[0])
        assert len(firsts) == 1

    def test_prose_and_json_arms_ask_for_different_forms(self):
        prose, as_json = FakeClient(), FakeClient()
        ExtractionAgent(prose, ARMS["A0-prose"], profile_for("openai")).run(ExtractionRequest("doc"))
        agent("A0-json", as_json).run(ExtractionRequest("doc"))
        assert "prose" in prose.system().lower()
        assert "JSON" in as_json.system()


class TestTheDecodeConstraint:
    def test_a1_sends_no_response_format(self):
        client = FakeClient()
        agent("A1", client).run(ExtractionRequest("doc", SCHEMA))
        assert client.response_format is None

    def test_a2_sends_one(self):
        client = FakeClient()
        agent("A2", client).run(ExtractionRequest("doc", SCHEMA))
        assert client.response_format is not None

    def test_a2_pins_the_class_to_the_catalogue(self):
        client = FakeClient()
        agent("A2", client).run(ExtractionRequest("doc", SCHEMA))
        assert client.response_format["properties"]["type"]["enum"] == list(CATALOGUE)

    def test_a_schema_with_no_class_slot_fails_loudly(self):
        """A silent no-op would run an arm unconstrained and call it constrained."""
        client = FakeClient()
        with pytest.raises(ValueError, match="no class property to pin"):
            agent("A2", client).run(ExtractionRequest("doc", {"type": "object", "properties": {"v": {}}}))

    def test_the_schema_actually_sent_is_hashed(self):
        client = FakeClient()
        result = agent("A2", client).run(ExtractionRequest("doc", SCHEMA))
        assert result.schema_sha256 and len(result.schema_sha256) == 64

    def test_two_providers_get_different_schemas(self):
        """Preparation is part of the treatment, so it has to be recorded."""
        strict = agent("A2", FakeClient(), profile="anthropic").run(ExtractionRequest("doc", SCHEMA))
        lenient = agent("A2", FakeClient(), profile="openai").run(ExtractionRequest("doc", SCHEMA))
        assert strict.schema_sha256 != lenient.schema_sha256
        assert strict.degradation is not None


class TestGrounding:
    def test_a3_keeps_the_context_where_a2_drops_it(self):
        grounded = {"@context": {"x": "http://example.org/"}, **SCHEMA}
        a2 = agent("A2", FakeClient()).run(ExtractionRequest("doc", grounded))
        a3 = agent("A3", FakeClient()).run(ExtractionRequest("doc", grounded))
        assert a2.degradation.semantics_dropped > 0
        assert a3.degradation.semantics_dropped == 0


class TestTheCommitGate:
    def test_an_entity_outside_the_catalogue_is_dropped(self):
        client = FakeClient('{"entities": [{"type": "quantities.Nonsense", "value": 1}]}')
        result = agent("A1", client).run(ExtractionRequest("doc", SCHEMA))
        assert result.payload["entities"] == []
        assert result.dropped == ["quantities.Nonsense"]

    def test_the_filtered_result_is_the_one_returned(self):
        """Keeping corrections and discarding removals is the predecessor's bug."""
        client = FakeClient('{"entities": [{"type": "quantities.Length", "value": 1}, {"type": "Nope", "value": 2}]}')
        result = agent("A1", client).run(ExtractionRequest("doc", SCHEMA))
        assert len(result.payload["entities"]) == 1

    def test_an_unambiguous_suffix_is_corrected_not_dropped(self):
        client = FakeClient('{"entities": [{"type": "Length", "value": 1}]}')
        result = agent("A1", client).run(ExtractionRequest("doc", SCHEMA))
        assert result.payload["entities"][0]["type"] == "quantities.Length"
        assert result.dropped == []

    def test_a0_has_no_gate(self):
        client = FakeClient('{"type": "anything at all", "value": 1}')
        result = agent("A0-json", client).run(ExtractionRequest("doc"))
        assert result.payload["type"] == "anything at all"
        assert result.dropped == []


class TestTheAnswer:
    def test_a_fenced_answer_still_parses(self):
        """Models fence JSON even when told not to."""
        client = FakeClient('```json\n{"type": "quantities.Length", "value": 1}\n```')
        assert agent("A1", client).run(ExtractionRequest("doc", SCHEMA)).parsed

    def test_malformed_json_is_not_repaired(self):
        """Repairing it would hide a failure of the decode-time constraint."""
        client = FakeClient('{"type": "Length", "value": ')
        result = agent("A2", client).run(ExtractionRequest("doc", SCHEMA))
        assert result.parsed is False

    def test_a_prose_arm_is_not_asked_to_parse(self):
        client = FakeClient("The length was one metre.")
        result = ExtractionAgent(client, ARMS["A0-prose"], profile_for("openai")).run(ExtractionRequest("doc"))
        assert result.text == "The length was one metre."
        assert client.calls == 1

    def test_a_json_arm_retries_a_malformed_answer(self):
        client = FakeClient("not json at all")
        agent("A1", client, attempts=3).run(ExtractionRequest("doc", SCHEMA))
        assert client.calls == 3

    def test_a_good_answer_is_not_retried(self):
        client = FakeClient('{"type": "quantities.Length", "value": 1}')
        agent("A1", client, attempts=3).run(ExtractionRequest("doc", SCHEMA))
        assert client.calls == 1


class TestTheRecord:
    def test_every_call_is_logged_with_its_tokens(self):
        client = FakeClient("not json")
        result = agent("A1", client, attempts=2).run(ExtractionRequest("doc", SCHEMA))
        assert len(result.calls) == 2
        assert result.calls.totals().input_tokens == 200
        assert [c.attempt for c in result.calls] == [1, 2]

    def test_the_record_is_serialisable(self):
        client = FakeClient()
        described = agent("A2", client).run(ExtractionRequest("doc", SCHEMA)).describe()
        assert json.dumps(described)
        assert described["parsed"] is True


class TestOrchestration:
    def test_single_shot_makes_one_call(self):
        client = FakeClient()
        agent("A1", client).run(ExtractionRequest("doc", SCHEMA))
        assert client.calls == 1

    def test_an_unported_orchestration_refuses_rather_than_pretending(self):
        with pytest.raises(NotImplementedError, match="not ported yet"):
            ExtractionAgent(
                FakeClient(),
                ARMS["A1"],
                profile_for("openai"),
                Orchestration.RECURSIVE,
            )


class TestParseJsonAnswer:
    @pytest.mark.parametrize(
        "text",
        ['{"a": 1}', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```', '  {"a": 1}  '],
    )
    def test_it_reads_the_shapes_models_produce(self, text):
        assert parse_json_answer(text) == {"a": 1}

    @pytest.mark.parametrize("text", ["", "   ", "sorry, I cannot", "{broken"])
    def test_it_returns_nothing_it_cannot_read(self, text):
        assert parse_json_answer(text) is None


def test_build_messages_needs_no_agent():
    condition = Enforcement(
        schema_in_prompt=False,
        catalogue=None,
        decode_constraint=DecodeConstraint.NONE,
        commit_gate=False,
        grounding=False,
        output_form=OutputForm.JSON,
    )
    messages = build_messages(ExtractionRequest("doc"), condition)
    assert [m.role for m in messages] == ["system", "user"]


class TestPinningTheUnitSlot:
    """A2 closes every slot the corpus closes, not only the class."""

    SCHEMA = {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "value": {"type": "number"},
                        "unit": {"type": "string"},
                    },
                },
            }
        },
    }

    def sent(self, enforcement):
        client = FakeClient('{"entities": []}')
        ExtractionAgent(client, enforcement, profile_for("openai")).run(
            ExtractionRequest(document="The reading was 1.0 meter.", schema=self.SCHEMA)
        )
        return client.response_format

    def unit_slot(self, schema):
        return schema["properties"]["entities"]["items"]["properties"]["unit"]

    def test_the_unit_slot_is_pinned_when_units_are_offered(self):
        schema = self.sent(arm("A2", ("Length",)).with_units(("meter", "foot")))
        assert self.unit_slot(schema)["enum"] == ["meter", "foot"]

    def test_the_unit_slot_is_left_open_when_none_are_offered(self):
        """A corpus that does not close the slot is a condition, not a fault."""
        assert "enum" not in self.unit_slot(self.sent(arm("A2", ("Length",))))

    def test_the_class_slot_is_still_pinned(self):
        schema = self.sent(arm("A2", ("Length",)).with_units(("meter",)))
        assert schema["properties"]["entities"]["items"]["properties"]["type"]["enum"] == ["Length"]

    def test_an_unconstrained_arm_sends_no_schema_at_all(self):
        assert self.sent(arm("A1", ("Length",)).with_units(("meter",))) is None

    def test_a_schema_with_no_unit_slot_is_refused(self):
        client = FakeClient('{"entities": []}')
        agent = ExtractionAgent(client, arm("A2", ("Length",)).with_units(("meter",)), profile_for("openai"))
        bare = {"type": "object", "properties": {"type": {"type": "string"}}}
        with pytest.raises(ValueError, match="no unit property"):
            agent.run(ExtractionRequest(document="d", schema=bare))
