"""Shortlist the class, then fill the schema that shortlist implies.

The orchestration exists because a corpus whose subclasses add properties
cannot be covered by one flat schema: the flat form is the union of every
property any class might carry, and it admits an answer no class allows.
"""

import json

import pytest

from oold.agent.client import ChatResponse
from oold.agent.enforcement import Orchestration, arm
from oold.agent.extraction import ExtractionAgent, _entities_of
from oold.agent.prompts import ExtractionRequest, build_selection_messages, selection_schema
from oold.agent.provider import profile_for

CATALOGUE = ("Length", "Mass", "Volume")

BRANCHES = {
    "Length": {"unit": {"type": "string", "enum": ["meter", "kilo_meter"]}},
    "Mass": {"unit": {"type": "string", "enum": ["gram"]}},
    "Volume": {"unit": {"type": "string", "enum": ["liter"]}},
}

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


class TwoStepClient:
    """Answers the select step, then the fill step, recording both."""

    model = "two-step"

    def __init__(self, candidates=("Length", "Mass"), answer="Length") -> None:
        self.candidates = list(candidates)
        self.answer = answer
        self.formats: list = []
        self.messages: list = []
        self.calls = 0

    def invoke(self, messages, *, response_format=None) -> ChatResponse:
        self.calls += 1
        self.formats.append(response_format)
        self.messages.append(list(messages))
        if self.calls == 1:
            payload = {"entities": [{"id": "e1", "candidates": self.candidates, "mention": "1.0 meter"}]}
        else:
            payload = {"entities": [{"type": self.answer, "value": 1.0, "unit": "meter"}]}
        return ChatResponse(text=json.dumps(payload), parsed=None)


def agent(client, k=2, name="A4"):
    return ExtractionAgent(
        client,
        arm(name, CATALOGUE),
        profile_for("openai"),
        Orchestration.SELECT_THEN_FILL,
        shortlist_k=k,
    )


def request():
    return ExtractionRequest(document="The reading was 1.0 meter.", schema=SCHEMA, branches=BRANCHES)


class TestTheSelectionSchema:
    def test_the_shortlist_is_capped_in_the_schema(self):
        """Wording alone would let it grow to the whole catalogue, and the
        second step would gain nothing."""
        built = selection_schema(CATALOGUE, 2)
        assert built["properties"]["entities"]["items"]["properties"]["candidates"]["maxItems"] == 2

    def test_candidates_come_from_the_catalogue(self):
        built = selection_schema(CATALOGUE, 2)
        items = built["properties"]["entities"]["items"]["properties"]["candidates"]["items"]
        assert items["enum"] == list(CATALOGUE)

    def test_the_mention_is_asked_for(self):
        built = selection_schema(CATALOGUE, 2)
        assert "mention" in built["properties"]["entities"]["items"]["properties"]

    def test_the_select_prompt_shows_the_same_catalogue(self):
        """The orchestrations differ in what is asked, not in what is shown."""
        content = build_selection_messages(request(), arm("A4", CATALOGUE), 2)[0].content
        assert all(f"- {name}" in content for name in CATALOGUE)

    def test_the_select_prompt_carries_the_document_alone(self):
        messages = build_selection_messages(request(), arm("A4", CATALOGUE), 2)
        assert messages[1].content == "The reading was 1.0 meter."


class TestTheTwoSteps:
    def test_exactly_two_calls_are_made(self):
        client = TwoStepClient()
        agent(client).run(request())
        assert client.calls == 2

    def test_both_calls_are_logged_by_step(self):
        """Per-step tokens are the only way to cost the orchestration."""
        client = TwoStepClient()
        result = agent(client).run(request())
        assert [c["step"] for c in result.calls.describe()["calls"]] == ["select", "fill"]

    def test_the_shortlist_is_recorded(self):
        result = agent(TwoStepClient()).run(request())
        assert result.selected == {"e1": ("Length", "Mass")}

    def test_the_fill_step_is_narrowed_to_the_shortlist(self):
        client = TwoStepClient()
        agent(client).run(request())
        items = client.formats[1]["properties"]["entities"]["items"]
        assert [b["properties"]["type"]["const"] for b in items["anyOf"]] == ["Length", "Mass"]

    def test_the_fill_step_sees_the_whole_document_again(self):
        """A step-one summary would be a bottleneck the grader cannot see past."""
        client = TwoStepClient()
        agent(client).run(request())
        assert client.messages[1][1].content == "The reading was 1.0 meter."

    def test_the_answer_survives(self):
        result = agent(TwoStepClient()).run(request())
        assert result.payload["entities"][0]["type"] == "Length"


class TestTheShortlistSize:
    def test_k_of_one_is_the_commit_case(self):
        client = TwoStepClient(candidates=["Length"])
        result = agent(client, k=1).run(request())
        assert result.selected == {"e1": ("Length",)}
        assert client.calls == 2

    def test_more_candidates_than_k_are_trimmed(self):
        """The model may ignore maxItems; the record must not."""
        client = TwoStepClient(candidates=["Length", "Mass", "Volume"])
        result = agent(client, k=2).run(request())
        assert result.selected == {"e1": ("Length", "Mass")}

    def test_a_shortlist_of_nothing_is_refused_at_construction(self):
        with pytest.raises(ValueError, match="no class to fill"):
            agent(TwoStepClient(), k=0)

    def test_a_candidate_outside_the_catalogue_is_dropped(self):
        client = TwoStepClient(candidates=["Length", "Invented"])
        result = agent(client).run(request())
        assert result.selected == {"e1": ("Length",)}


class TestWhenSelectionFails:
    def test_an_empty_shortlist_stops_before_the_fill_call(self):
        """Spending the second call on a union of nothing would fail anyway."""
        client = TwoStepClient(candidates=[])
        result = agent(client).run(request())
        assert client.calls == 1
        assert result.payload is None

    def test_an_empty_shortlist_is_still_recorded(self):
        """So the failure is attributable to the select step."""
        result = agent(TwoStepClient(candidates=[])).run(request())
        assert result.selected == {"e1": ()}

    def test_a_missing_catalogue_is_refused(self):
        client = TwoStepClient()
        bare = ExtractionAgent(client, arm("A0-json"), profile_for("openai"), Orchestration.SELECT_THEN_FILL)
        with pytest.raises(ValueError, match="needs a catalogue"):
            bare.run(request())


class TestTheOtherOrchestrations:
    def test_single_shot_still_makes_one_call(self):
        client = TwoStepClient()
        ExtractionAgent(client, arm("A4", CATALOGUE), profile_for("openai")).run(request())
        assert client.calls == 1

    def test_the_recursive_orchestration_says_it_is_not_ported(self):
        with pytest.raises(NotImplementedError, match="entity graph"):
            ExtractionAgent(TwoStepClient(), arm("A4", CATALOGUE), profile_for("openai"), Orchestration.RECURSIVE)


class MultiEntityClient:
    """Shortlists different classes for two entities, then answers."""

    model = "multi"

    def __init__(self, first=("Length",), second=("Mass",)) -> None:
        self.first = list(first)
        self.second = list(second)
        self.formats: list = []
        self.messages: list = []
        self.calls = 0

    def invoke(self, messages, *, response_format=None) -> ChatResponse:
        self.calls += 1
        self.formats.append(response_format)
        self.messages.append(list(messages))
        if self.calls == 1:
            payload = {
                "entities": [
                    {"id": "e1", "candidates": self.first, "mention": "1.0 meter"},
                    {"id": "e2", "candidates": self.second, "mention": "2.0 gram"},
                ]
            }
        else:
            offered = self.formats[-1]["properties"]["entities"]["items"]
            names = [b["properties"]["type"]["const"] for b in offered["anyOf"]]
            payload = {"entities": [{"type": names[0], "value": 1.0, "unit": "meter"}]}
        return ChatResponse(text=json.dumps(payload), parsed=None)


class TestOneCallPerShortlist:
    """Pooling every entity's candidates lets entity A be answered with
    entity B's class, which is the thing the shortlist was for."""

    def run(self, client, k=2):
        return ExtractionAgent(
            client,
            arm("A4", CATALOGUE),
            profile_for("openai"),
            Orchestration.SELECT_THEN_FILL,
            shortlist_k=k,
        ).run(request())

    def test_two_shortlists_get_two_fill_calls(self):
        client = MultiEntityClient()
        self.run(client)
        assert client.calls == 3

    def test_each_fill_call_offers_only_its_own_classes(self):
        client = MultiEntityClient()
        self.run(client)
        offered = [
            [b["properties"]["type"]["const"] for b in fmt["properties"]["entities"]["items"]["anyOf"]]
            for fmt in client.formats[1:]
        ]
        assert offered == [["Length"], ["Mass"]]

    def test_entities_that_shortlist_the_same_classes_share_a_call(self):
        """A single-entity document still costs one fill call."""
        client = MultiEntityClient(first=("Length",), second=("Length",))
        self.run(client)
        assert client.calls == 2

    def test_a_split_call_says_which_entity_it_is_for(self):
        """Named by the words the select step read it from, because an
        identifier it invented means nothing to a model reading again."""
        client = MultiEntityClient()
        self.run(client)
        assert "1.0 meter" in client.messages[1][0].content

    def test_a_single_group_sends_the_unchanged_instruction(self):
        client = MultiEntityClient(first=("Length",), second=("Length",))
        self.run(client)
        assert "report only the entities" not in client.messages[1][0].content

    def test_every_answer_is_merged(self):
        client = MultiEntityClient()
        result = self.run(client)
        assert len(result.payload["entities"]) == 2

    def test_the_shortlist_is_still_recorded_per_entity(self):
        result = self.run(MultiEntityClient())
        assert result.selected == {"e1": ("Length",), "e2": ("Mass",)}


def test_the_selection_schema_is_named():
    """A structured-output call names a tool after the schema title, so a
    schema without one is refused before anything is sent. The first live
    select-then-fill run failed every cell on it."""
    built = selection_schema(CATALOGUE, 3)
    assert built.get("title")
    assert built.get("description")


class TestTheAnswerWrapperAModelChooses:
    """Where the entity list is found when the model names it something else.

    Measured on 16 gpt-5-nano selections: 3 came back as
    ``{"EntityCandidates": [...]}`` with correct entities inside, and each one
    scored zero because no wrapper name matched. The title was added to the
    selection schema to stop LangChain rejecting it, so one fix caused the
    next fault.
    """

    def test_the_declared_wrapper_is_preferred(self):
        payload = {"entities": [{"id": "e1"}], "other": [{"id": "e2"}]}
        assert _entities_of(payload) == [{"id": "e1"}]

    def test_a_lone_key_holding_objects_is_the_wrapper(self):
        payload = {"EntityCandidates": [{"id": "e1", "candidates": ["Seat"]}]}
        assert _entities_of(payload) == [{"id": "e1", "candidates": ["Seat"]}]

    def test_an_echoed_schema_is_not_an_answer(self):
        """The other failure mode, and it must stay a failure.

        A model that returns the schema it was given has not answered, and
        reading its ``properties`` as entities would score that as an
        extraction.
        """
        payload = {"type": "object", "properties": {"entities": {"type": "array"}}}
        assert _entities_of(payload) == []

    def test_a_lone_key_holding_scalars_is_not_a_wrapper(self):
        assert _entities_of({"candidates": ["Seat", "Book"]}) == []


def test_the_select_prompt_says_what_one_entity_is():
    """The wording that stops the step returning one entity per mention.

    Asserted because the whole four-orchestration grid was scored on a prompt
    that asked for "every entity it describes" and never said an entity is a
    thing rather than a statement about one. Every orchestration lost to
    single shot, and the detect step was planning 7.6 entities for a document
    holding two.

    The count is deliberately absent. The step is asked how many entities a
    document describes, so a prompt that said would be answering it.
    """
    request = ExtractionRequest(document="anything", schema=None)
    system = build_selection_messages(request, arm("A2", CATALOGUE), 3)[0].content

    assert "not a statement about one" in system
    assert "one entity, not four" in system
    for leak in ("two entities", "2 entities", "exactly two"):
        assert leak not in system.lower()
