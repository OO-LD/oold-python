"""The commit gate, and the difference between filtering and validating.

Until this existed, ``commit_gate`` checked a class name against a list and
nothing else. Reporting that as commit-time validation would be the
predecessor's construct failure one level in: an arm labelled as a conformance
check that performs a string match, so the contrast it anchors is not the
contrast its name claims.
"""

import json
from dataclasses import replace

from oold.agent.client import ChatResponse
from oold.agent.enforcement import arm
from oold.agent.extraction import ExtractionAgent
from oold.agent.prompts import ExtractionRequest
from oold.agent.provider import profile_for
from oold.agent.repair import repair_message

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
                "required": ["type", "value", "unit"],
            },
        }
    },
}

WHOLE = {"entities": [{"type": "Length", "value": 1.0, "unit": "meter"}]}
MISSING = {"entities": [{"type": "Length"}]}
WRONG_TYPE = {"entities": [{"type": "Length", "value": "one", "unit": "meter"}]}


class ScriptedClient:
    """Answers from a list, repeating the last answer once exhausted."""

    model = "scripted"

    def __init__(self, *answers) -> None:
        self.answers = [json.dumps(a) for a in answers]
        self.calls = 0
        self.turns: list[int] = []
        self.last: list = []

    def invoke(self, messages, *, response_format=None, strict=False) -> ChatResponse:
        self.calls += 1
        self.turns.append(len(messages))
        self.last = list(messages)
        index = min(self.calls - 1, len(self.answers) - 1)
        return ChatResponse(text=self.answers[index], parsed=None)


def run(client, *, attempts=0, name="A1"):
    base = arm(name) if name.startswith("A0") else arm(name, ("Length",))
    enforcement = replace(base, repair_attempts=attempts)
    agent = ExtractionAgent(client, enforcement, profile_for("openai"))
    return agent.run(ExtractionRequest(document="d", schema=SCHEMA))


class TestValidatingTheAnswer:
    def test_a_conforming_answer_reports_no_errors(self):
        assert run(ScriptedClient(WHOLE)).invalid == []

    def test_a_missing_required_property_is_caught(self):
        """The string filter passes this: the class name is in the catalogue."""
        result = run(ScriptedClient(MISSING))
        assert result.invalid
        assert any("required property" in reason for reason in result.invalid)

    def test_a_wrong_type_is_caught(self):
        assert run(ScriptedClient(WRONG_TYPE)).invalid

    def test_the_invalid_answer_is_kept_not_discarded(self):
        """Returning the last valid answer instead would report a conformance
        rate the arm did not achieve."""
        assert run(ScriptedClient(MISSING)).payload == MISSING

    def test_an_arm_that_does_not_validate_reports_nothing(self):
        result = run(ScriptedClient(MISSING), name="A0-json")
        assert result.invalid == []

    def test_the_arms_that_claim_a_commit_gate_validate(self):
        for name in ("A1", "A2", "A2-enforced-only", "A3", "A4"):
            assert arm(name, ("Length",)).validate_output is True

    def test_the_arms_that_claim_nothing_do_not(self):
        for name in ("A0-json", "A0-prose"):
            assert arm(name).validate_output is False


class TestRepairing:
    def test_no_repair_is_attempted_by_default(self):
        """Validating and repairing are different claims, so the count is part
        of the condition."""
        client = ScriptedClient(MISSING, WHOLE)
        result = run(client, attempts=0)
        assert client.calls == 1
        assert result.repairs == 0

    def test_one_repair_fixes_a_fixable_answer(self):
        client = ScriptedClient(MISSING, WHOLE)
        result = run(client, attempts=1)
        assert client.calls == 2
        assert result.repairs == 1
        assert result.invalid == []
        assert result.payload == WHOLE

    def test_the_repair_call_is_logged_as_its_own_step(self):
        client = ScriptedClient(MISSING, WHOLE)
        result = run(client, attempts=1)
        assert [c["step"] for c in result.calls.describe()["calls"]] == ["extract", "repair"]

    def test_a_conforming_answer_costs_no_repair_call(self):
        client = ScriptedClient(WHOLE)
        result = run(client, attempts=3)
        assert client.calls == 1
        assert result.repairs == 0

    def test_repairs_stop_at_the_declared_limit(self):
        """A model that never conforms would otherwise loop on the budget."""
        client = ScriptedClient(MISSING)
        result = run(client, attempts=2)
        assert client.calls == 3
        assert result.repairs == 2
        assert result.invalid

    def test_a_failed_repair_is_reported_not_hidden(self):
        result = run(ScriptedClient(MISSING), attempts=1)
        assert result.repairs == 1
        assert result.invalid

    def test_the_repair_turn_carries_the_original_messages(self):
        """So the model is not asked to repair something out of context."""
        client = ScriptedClient(MISSING, WHOLE)
        run(client, attempts=1)
        assert client.turns == [2, 3]

    def test_the_repair_turn_carries_the_errors(self):
        client = ScriptedClient(MISSING, WHOLE)
        run(client, attempts=1)
        assert "required property" in client.last[-1].content


class TestTheRepairMessage:
    def test_it_carries_the_answer_and_the_reasons(self):
        message = repair_message('{"a": 1}', ["at /a: wrong"])
        assert '{"a": 1}' in message.content
        assert "at /a: wrong" in message.content

    def test_it_is_a_user_turn(self):
        assert repair_message("{}", ["x"]).role == "user"

    def test_a_long_error_list_is_capped(self):
        """A wide schema can fail on every property of every entity, and a
        thousand near-identical lines would crowd out the answer."""
        message = repair_message("{}", [f"error {i}" for i in range(50)], limit=5)
        assert "and 45 more" in message.content
        assert message.content.count("- error") == 5


class TestWhatTheRecordSays:
    def test_the_record_carries_the_errors_and_the_repair_count(self):
        described = run(ScriptedClient(MISSING), attempts=0).describe()
        assert described["repairs"] == 0
        assert described["invalid"]

    def test_the_condition_says_whether_it_validated(self):
        described = arm("A1", ("Length",)).describe()
        assert described["validate_output"] is True
        assert described["repair_attempts"] == 0

    def test_the_record_is_serialisable(self):
        assert json.dumps(run(ScriptedClient(MISSING), attempts=1).describe())


def test_the_gate_and_the_validator_catch_different_things():
    """The point of the whole file. A class outside the catalogue is a gate
    failure; a missing required property is a validation failure; neither
    catches the other."""
    gate_only = run(ScriptedClient({"entities": [{"type": "Nonesuch", "value": 1.0, "unit": "m"}]}))
    assert gate_only.dropped == ["Nonesuch"]
    assert gate_only.invalid == []

    validator_only = run(ScriptedClient(MISSING))
    assert validator_only.dropped == []
    assert validator_only.invalid
