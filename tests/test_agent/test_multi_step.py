"""Detect, choose properties per entity, extract, link.

Segmented with one call inserted between the plan and the fill. The plan closes
the class slot, the property step closes which slots exist at all, and the
extract step fills what is left against ids both ends agree on.

The question the arm exists to answer is whether closing the property slot per
entity buys anything, given that segmented already loses to single shot because
a wrong plan is unrecoverable. This adds a second step that binds, so it
inherits that risk and doubles it. What it does not inherit is the plan call
that answers with the schema instead of a plan, which is asked again here.
"""

import json
from dataclasses import replace

import pytest

from oold.agent.client import ChatResponse, TokenUsage
from oold.agent.enforcement import Orchestration, arm
from oold.agent.extraction import Edge, ExtractionAgent, PlannedEntity
from oold.agent.prompts import ExtractionRequest, property_schema
from oold.agent.provider import profile_for

CATALOGUE = ("Person", "Organization", "LocalBusiness", "Book")

BRANCHES = {
    "Thing": {"name": {"type": "string"}},
    "Person": {"jobTitle": {"type": "string"}, "worksFor": {"type": "object"}},
    "Organization": {"legalName": {"type": "string"}},
    "LocalBusiness": {"openingHours": {"type": "string"}},
    "Book": {"isbn": {"type": "string"}, "author": {"type": "object"}},
}

PARENTS = {
    "Person": ("Thing",),
    "Organization": ("Thing",),
    "LocalBusiness": ("Organization",),
    "Book": ("Thing",),
}

RANGES = {"worksFor": ("Organization",), "author": ("Person",)}

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Entities",
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "jobTitle": {"type": "string"},
                    "legalName": {"type": "string"},
                    "openingHours": {"type": "string"},
                    "isbn": {"type": "string"},
                    "worksFor": {"type": "object"},
                    "author": {"type": "object"},
                },
                "required": ["type"],
            },
        }
    },
    "required": ["entities"],
}

DOCUMENT = "Ada works for Acme. Acme is a company. The Ada Book was written by Ada."

PLAN = [
    {"id": "e1", "candidates": ["Person"], "mention": "Ada"},
    {"id": "e2", "candidates": ["Organization"], "mention": "Acme"},
]

FILLABLE = {
    "fillable": {
        "e1": [
            {"property": "name", "stated": "Ada"},
            {"property": "worksFor", "stated": "Acme"},
        ],
        "e2": [{"property": "name", "stated": "Acme"}],
    }
}

EXTRACTED = [
    [{"id": "e1", "type": "Person", "name": "Ada", "worksFor": "e2"}],
    [{"id": "e2", "type": "Organization", "name": "Acme"}],
]

SCHEMA_ECHO = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "EntityCandidates",
    "type": "object",
    "properties": {"entities": {"type": "array", "items": {"type": "object"}}},
    "required": ["entities"],
}
"""What gpt-5-nano answered on 37 of 120 plan calls: the schema it was asked
for, rather than an instance of it."""

UNION_PLAN = [
    {"id": "e1", "candidates": ["Person", "Book"], "mention": "Ada"},
    {"id": "e2", "candidates": ["Organization", "LocalBusiness"], "mention": "Acme"},
]
"""Two classes per entity, so every extract call is sent a union of two
branches and a profile that refuses ``anyOf`` has something to lose."""


class MultiStepClient:
    """Answers the detect step, the property step, then one call per group."""

    model = "stepper"

    def __init__(self, plan=None, fillable=None, answers=None, detects=None) -> None:
        self.detects = list(detects) if detects is not None else [{"entities": list(PLAN if plan is None else plan)}]
        self.fillable = FILLABLE if fillable is None else fillable
        self.answers = [list(group) for group in (EXTRACTED if answers is None else answers)]
        self.asked_properties = False
        self.formats: list = []
        self.messages: list = []
        self.calls = 0

    def invoke(self, messages, *, response_format=None, strict=False) -> ChatResponse:
        self.calls += 1
        self.formats.append(response_format)
        self.messages.append(list(messages))
        if self.detects:
            payload = self.detects.pop(0)
        elif not self.asked_properties:
            self.asked_properties = True
            payload = self.fillable
        else:
            payload = {"entities": self.answers.pop(0) if self.answers else []}
        return ChatResponse(
            text=json.dumps(payload),
            parsed=None,
            usage=TokenUsage(input_tokens=100, output_tokens=10),
        )


def agent(client, name="schema-dump-catalog-flat-enforced", profile="openai", k=2, **kwargs):
    return ExtractionAgent(
        client,
        arm(name, CATALOGUE),
        profile_for(profile),
        Orchestration.MULTI_STEP,
        shortlist_k=k,
        **kwargs,
    )


def request(ranges=RANGES):
    return ExtractionRequest(
        document=DOCUMENT,
        schema=SCHEMA,
        branches=BRANCHES,
        parents=PARENTS,
        ranges=ranges,
    )


def items_of(response_format):
    """The entity shape an extract call was sent, union or object."""
    return response_format["properties"]["entities"]["items"]


def targets_of(slot):
    """The ids a pinned slot offers, without the null that lets it decline."""
    return [value for value in slot["enum"] if value is not None]


def enums_of(response_format):
    """The property enumeration each entity was offered, per entity."""
    offered = response_format["properties"]["fillable"]["properties"]
    return {key: slot["items"]["enum"] for key, slot in offered.items()}


def _sentence_about_several_values(content):
    """The one sentence of an extract prompt that allows several values."""
    return next(part for part in content.split(". ") if "more than one value" in part)


class TestTheCallsItMakes:
    def test_one_detect_one_property_call_and_one_extract_per_group(self):
        client = MultiStepClient()
        agent(client).run(request())
        assert client.calls == 4

    def test_the_steps_are_named_apart_in_the_log(self):
        """Per-step tokens are the only way to cost the orchestration, and the
        property step is the one thing this has that segmented does not."""
        result = agent(MultiStepClient()).run(request())
        assert [c["step"] for c in result.calls.describe()["calls"]] == [
            "detect",
            "properties",
            "extract",
            "extract",
        ]

    def test_tokens_are_attributed_to_the_step_that_spent_them(self):
        by_step = agent(MultiStepClient()).run(request()).calls.by_step()
        assert by_step["detect"].input_tokens == 100
        assert by_step["properties"].input_tokens == 100
        assert by_step["extract"].input_tokens == 200

    def test_entities_that_agree_on_class_and_properties_share_an_extract_call(self):
        client = MultiStepClient(
            plan=[
                {"id": "e1", "candidates": ["Person"], "mention": "Ada"},
                {"id": "e2", "candidates": ["Person"], "mention": "Grace"},
            ],
            fillable={"fillable": {"e1": ["name"], "e2": ["name"]}},
            answers=[[{"id": "e1", "type": "Person"}, {"id": "e2", "type": "Person"}]],
        )
        agent(client).run(request())
        assert client.calls == 3

    def test_entities_that_chose_different_properties_do_not(self):
        """Entities sharing a call share the schema that call is sent, so two
        that chose different properties can no more share one than two that
        shortlisted different classes."""
        client = MultiStepClient(
            plan=[
                {"id": "e1", "candidates": ["Person"], "mention": "Ada"},
                {"id": "e2", "candidates": ["Person"], "mention": "Grace"},
            ],
            fillable={"fillable": {"e1": ["name"], "e2": ["name", "jobTitle"]}},
            answers=[[{"id": "e1", "type": "Person"}], [{"id": "e2", "type": "Person"}]],
        )
        agent(client).run(request())
        assert client.calls == 4

    def test_a_plan_that_placed_nothing_stops_before_the_property_call(self):
        client = MultiStepClient(plan=[{"id": "e1", "candidates": [], "mention": "Ada"}])
        result = agent(client).run(request())
        assert client.calls == 1
        assert result.payload is None

    def test_the_detect_step_asks_the_selection_question(self):
        client = MultiStepClient()
        agent(client).run(request())
        assert client.formats[0]["title"] == "EntityCandidates"


class TestThePerEntityPropertyEnum:
    def sent(self, client=None):
        client = client or MultiStepClient()
        agent(client).run(request())
        return client

    def test_the_property_schema_carries_one_array_per_entity(self):
        assert sorted(enums_of(self.sent().formats[1])) == ["e1", "e2"]

    def test_the_enum_holds_only_that_entity_s_own_properties(self):
        """The direct analogue of closing the class slot. Pooling every
        entity's properties into one enumeration would let one entity be given
        another's property, which is the thing a per-entity enumeration is
        for."""
        offered = enums_of(self.sent().formats[1])
        assert offered["e1"] == ["name", "jobTitle", "worksFor"]
        assert offered["e2"] == ["name", "legalName"]

    def test_a_property_another_entity_s_class_declares_is_absent(self):
        offered = enums_of(self.sent().formats[1])
        assert "jobTitle" not in offered["e2"]
        assert "legalName" not in offered["e1"]

    def test_an_inherited_property_is_offered(self):
        """`name` is declared on Thing, and Person and Organization both carry
        it, so a union over the shortlist has to walk the ancestry."""
        assert "name" in enums_of(self.sent().formats[1])["e1"]

    def test_a_shortlist_offers_the_union_of_its_classes_properties(self):
        """The extract step has not committed to one class yet, and offering
        only the first would rule out a value the second may well state."""
        client = MultiStepClient(plan=UNION_PLAN, fillable={"fillable": {"e1": ["name"], "e2": ["name"]}})
        agent(client).run(request())
        assert enums_of(client.formats[1])["e1"] == ["name", "jobTitle", "isbn", "worksFor", "author"]

    def test_the_property_schema_carries_a_title(self):
        """LangChain rejects a response format without one, and every cell of
        the arm then fails without saying why."""
        assert self.sent().formats[1]["title"] == "FillableProperties"

    def test_the_prompt_names_each_entity_with_its_class_and_its_properties(self):
        content = self.sent().messages[1][0].content
        assert 'e1 ("Ada"), Person: name, jobTitle, worksFor' in content

    def test_the_property_step_reads_the_whole_document(self):
        assert self.sent().messages[1][1].content == DOCUMENT

    def test_the_chosen_properties_are_recorded_per_entity(self):
        """So a failure stays attributable to a step. Without it, never
        offering the property and leaving it empty are the same missing
        value."""
        result = agent(MultiStepClient()).run(request())
        assert result.properties_chosen == {"e1": ("name", "worksFor"), "e2": ("name",)}

    def test_a_name_outside_the_entity_s_enumeration_is_dropped(self):
        client = MultiStepClient(fillable={"fillable": {"e1": ["name", "legalName"], "e2": ["name"]}})
        result = agent(client).run(request())
        assert result.properties_chosen["e1"] == ("name",)

    def test_an_entity_with_no_properties_is_refused_rather_than_enumerated_empty(self):
        """An empty enum is unsatisfiable rather than tight: the strict subsets
        reject it, and one that accepted it would leave a required array with
        no legal member."""
        with pytest.raises(ValueError, match="admit nothing"):
            property_schema({"e1": ()})

    def test_the_record_is_serialisable(self):
        described = agent(MultiStepClient()).run(request()).describe()
        assert json.dumps(described)
        assert described["properties_chosen"] == {"e1": ["name", "worksFor"], "e2": ["name"]}


class TestWhatTheExtractStepIsGiven:
    def sent(self, client=None, **kwargs):
        client = client or MultiStepClient()
        agent(client, **kwargs).run(request())
        return client

    def test_the_extract_step_sees_the_whole_document_again(self):
        assert self.sent().messages[2][1].content == DOCUMENT

    def test_the_prompt_names_the_entities_it_is_for_by_id(self):
        assert 'e1 ("Ada")' in self.sent().messages[2][0].content

    def test_the_prompt_names_the_properties_to_fill(self):
        """Named even though the schema already carries only them, as the ids
        are named even though the id slot is already enumerated."""
        assert "Report only these properties for them: name, worksFor." in self.sent().messages[2][0].content

    def test_the_schema_carries_the_chosen_properties(self):
        assert "worksFor" in items_of(self.sent().formats[2])["properties"]

    def test_a_property_the_step_left_out_is_gone_from_the_schema(self):
        """Closing the property slot, which is what the step is for."""
        offered = items_of(self.sent().formats[2])["properties"]
        assert "jobTitle" not in offered
        assert "legalName" not in offered

    def test_a_required_property_survives_the_trim(self):
        """Dropping it leaves a name in `required` with nothing to satisfy it,
        and a subset that rewrites `required` from `properties` would instead
        make the answer legal without it."""
        assert "type" in items_of(self.sent().formats[2])["properties"]

    def test_an_entity_the_step_left_empty_is_asked_for_its_class_alone(self):
        """What the step said. Restoring the slots behind its back would hide a
        step-two failure inside step three.

        The plan read no mention for this one, so nothing outside the step has
        anything to say about the name slot either."""
        client = MultiStepClient(
            plan=[{"id": "e1", "candidates": ["Person"], "mention": ""}],
            fillable={"fillable": {"e1": []}},
            answers=[[{"id": "e1", "type": "Person"}]],
        )
        agent(client).run(request())
        assert sorted(items_of(client.formats[2])["properties"]) == ["id", "type"]
        assert "no property value" in client.messages[2][0].content

    def test_an_open_condition_keeps_the_schema_whole(self):
        """The same two calls, with the answer advisory instead of binding. A
        property the step missed can still be answered, which is the claim the
        closed condition is measured against."""
        client = self.sent(close_properties=False)
        assert "jobTitle" in items_of(client.formats[2])["properties"]

    def test_an_open_condition_still_names_the_properties(self):
        assert "Report only these properties" in self.sent(close_properties=False).messages[2][0].content

    def test_the_prompt_says_a_property_may_hold_more_than_one_value(self):
        """The answer shape declares every slot as an array, so the shape
        permits several and only the wording was silent. Told nothing, models
        answer with the first value alone."""
        content = self.sent().messages[2][0].content
        assert "Where the document states more than one value for a property, give every one of them." in content

    def test_it_says_neither_which_property_nor_how_many_values(self):
        """How many values a document states is part of what is being
        measured, and a count named for one property would answer it."""
        sentence = _sentence_about_several_values(self.sent().messages[2][0].content)
        assert not any(character.isdigit() for character in sentence)
        assert not any(name in sentence for name in ("name", "worksFor", "jobTitle", "isbn"))


class TestTheIdSlot:
    def sent(self):
        client = MultiStepClient()
        agent(client).run(request())
        return client

    def test_an_extract_call_is_pinned_to_the_ids_it_is_for(self):
        client = self.sent()
        assert items_of(client.formats[2])["properties"]["id"]["enum"] == ["e1"]
        assert items_of(client.formats[3])["properties"]["id"]["enum"] == ["e2"]

    def test_the_id_is_required(self):
        assert "id" in items_of(self.sent().formats[2])["required"]

    def test_the_id_survives_the_property_trim(self):
        """It was never offered to the property step, because it is how the
        answer is joined back to the plan and not a value to fill."""
        assert "id" in items_of(self.sent().formats[2])["properties"]


class TestPinningAReference:
    def sent(self, client=None):
        client = client or MultiStepClient()
        agent(client).run(request())
        return client

    def test_only_a_compatible_entity_is_offered(self):
        assert targets_of(items_of(self.sent().formats[2])["properties"]["worksFor"]) == ["e2"]

    def test_an_entity_whose_class_is_not_in_the_range_is_absent(self):
        assert "e1" not in targets_of(items_of(self.sent().formats[2])["properties"]["worksFor"])

    def test_a_reference_the_property_step_left_out_is_not_reported_as_left_open(self):
        """A slot that is not offered is not a slot left open. The property
        step removing it is the same case as a provider's optional-property
        limit removing it."""
        client = MultiStepClient(fillable={"fillable": {"e1": ["name"], "e2": ["name"]}})
        result = agent(client).run(request())
        assert "worksFor" not in items_of(client.formats[2])["properties"]
        assert result.unpinned == []

    def test_a_range_no_planned_entity_fits_is_recorded_as_left_open(self):
        client = MultiStepClient(
            plan=[{"id": "e1", "candidates": ["Person"], "mention": "Ada"}],
            fillable={"fillable": {"e1": ["name", "worksFor"]}},
            answers=[[{"id": "e1", "type": "Person", "name": "Ada"}]],
        )
        result = agent(client).run(request())
        assert result.unpinned == ["worksFor"]

    def test_an_unconstrained_arm_pins_no_reference(self):
        client = MultiStepClient()
        agent(client, name="schema-dump-catalog-not-enforced-gated").run(request())
        assert client.formats[2] is None


class TestTheLinkSurvives:
    def test_the_payload_carries_the_link(self):
        result = agent(MultiStepClient()).run(request())
        by_id = {entity["id"]: entity for entity in result.payload["entities"]}
        assert by_id["e1"]["worksFor"] == "e2"

    def test_every_planned_entity_is_merged_into_one_answer(self):
        result = agent(MultiStepClient()).run(request())
        assert sorted(e["id"] for e in result.payload["entities"]) == ["e1", "e2"]

    def test_the_link_is_recorded_as_an_edge(self):
        assert agent(MultiStepClient()).run(request()).links == [Edge(source="e1", prop="worksFor", target="e2")]

    def test_a_resolved_link_is_not_dangling(self):
        assert agent(MultiStepClient()).run(request()).dangling == []

    def test_an_unreported_target_leaves_the_edge_dangling(self):
        """The edge is kept and flagged. An answer pointing at an entity it
        never reported is a different failure from an answer reporting no edge,
        and dropping it would make the two the same number."""
        result = agent(MultiStepClient(answers=[EXTRACTED[0], []])).run(request())
        assert result.dangling == [Edge(source="e1", prop="worksFor", target="e2")]
        assert result.payload["entities"][0]["worksFor"] == "e2"


class TestWhatEachProviderGets:
    """The trimmed and pinned schema under two subsets, with what it cost.

    The trim happens before the provider transform and the pins after, as they
    do for segmented, so the fidelity figure is the transform's alone. What it
    says is that the same condition costs different amounts on different
    providers, which is why cells of differing fidelity are never averaged.
    """

    def sent(self, profile):
        client = MultiStepClient(
            plan=UNION_PLAN,
            fillable={"fillable": {"e1": ["name", "worksFor"], "e2": ["name"]}},
            answers=[[{"id": "e1", "type": "Person", "worksFor": "e2"}], [{"id": "e2", "type": "Organization"}]],
        )
        result = agent(client, name="schema-dump-catalog-enforced", profile=profile).run(request())
        return items_of(client.formats[2]), result.degradation

    def test_a_profile_that_takes_anyof_keeps_the_union_and_the_pin(self):
        items, degradation = self.sent("openai")
        branch = next(b for b in items["anyOf"] if "worksFor" in b["properties"])
        assert targets_of(branch["properties"]["worksFor"]) == ["e2"]
        assert degradation.dropped.get("anyOf") is None

    def test_the_branches_are_trimmed_with_the_answer_shape(self):
        """A branch still declaring a property the shape no longer carries
        would put it back on the union arm alone, and the difference between
        the arms would be a difference in what each was asked for."""
        items, _ = self.sent("openai")
        assert all("isbn" not in branch["properties"] for branch in items["anyOf"])

    def test_the_pinned_id_reaches_every_branch(self):
        items, _ = self.sent("openai")
        assert all(targets_of(branch["properties"]["id"]) == ["e1"] for branch in items["anyOf"])

    def test_a_profile_that_refuses_anyof_still_gets_the_pin(self):
        items, _ = self.sent("anthropic")
        assert "anyOf" not in items
        assert targets_of(items["properties"]["worksFor"]) == ["e2"]

    def test_refusing_anyof_is_recorded_as_a_loss(self):
        _, degradation = self.sent("anthropic")
        assert degradation.dropped.get("anyOf") == 1
        assert degradation.fidelity < 1.0

    def test_the_two_profiles_report_different_fidelity(self):
        _, keeps = self.sent("openai")
        _, loses = self.sent("anthropic")
        assert loses.fidelity < keeps.fidelity


class TestAskingAgain:
    """The first call that answered with the schema instead of an answer.

    gpt-5-nano returned the selection schema on 37 of 120 plan calls under a
    segmented flat-enforced arm and on none at all under the same arm single
    shot, because a single-shot arm has no call whose answer is a structure.
    It costs the whole cell: the
    classes the plan did not choose are the classes the later steps may not
    answer with.
    """

    def test_a_schema_answer_is_asked_again(self):
        client = MultiStepClient(detects=[SCHEMA_ECHO, {"entities": PLAN}])
        result = agent(client).run(request())
        assert result.selected == {"e1": ("Person",), "e2": ("Organization",)}

    def test_the_second_ask_is_logged_under_the_same_step(self):
        """One extra call on the calls that failed, and countable, because an
        arm that spends a call more than another and does not say so is
        reported as cheaper than it was."""
        client = MultiStepClient(detects=[SCHEMA_ECHO, {"entities": PLAN}])
        result = agent(client).run(request())
        logged = [(c["step"], c["attempt"]) for c in result.calls.describe()["calls"]]
        assert logged[:2] == [("detect", 1), ("detect", 2)]

    def test_it_hands_the_validator_s_reasons_back_verbatim(self):
        """As an invalid extraction already does, so the retry rate stays a
        measure of the model and not of how the advice was worded."""
        client = MultiStepClient(detects=[SCHEMA_ECHO, {"entities": PLAN}])
        agent(client).run(request())
        assert "does not satisfy the schema" in client.messages[1][-1].content

    def test_a_usable_answer_is_not_asked_again(self):
        client = MultiStepClient()
        agent(client).run(request())
        assert client.calls == 4

    def test_an_answer_under_an_undeclared_wrapper_is_left_alone(self):
        """Naming a schema stopped one provider rejecting it and started
        another answering under that title. Those entities are usable, and
        asking again would spend a call to replace a good answer."""
        client = MultiStepClient(detects=[{"EntityCandidates": PLAN}])
        result = agent(client).run(request())
        assert result.selected == {"e1": ("Person",), "e2": ("Organization",)}
        assert client.calls == 4

    def test_a_document_with_nothing_in_it_is_not_asked_again(self):
        """An answer that validates and names no entity is a document with
        nothing in it, not a failed call."""
        client = MultiStepClient(detects=[{"entities": []}])
        result = agent(client).run(request())
        assert client.calls == 1
        assert result.payload is None

    def test_an_answer_that_is_still_wrong_is_kept_as_it_came(self):
        client = MultiStepClient(detects=[SCHEMA_ECHO, SCHEMA_ECHO])
        result = agent(client).run(request())
        assert client.calls == 2
        assert result.payload is None


class TestTheOtherOrchestrationsAreUnchanged:
    def test_segmented_does_not_ask_again_by_default(self):
        """There are grids depending on the three orchestrations already
        measured, and a retry added to one of them would make the stored
        numbers and the new ones different arms under one name."""
        client = MultiStepClient(detects=[SCHEMA_ECHO])
        ExtractionAgent(
            client,
            arm("schema-dump-catalog-flat-enforced", CATALOGUE),
            profile_for("openai"),
            Orchestration.SEGMENTED,
            shortlist_k=2,
        ).run(request())
        assert client.calls == 1

    def test_segmented_asks_again_when_it_is_told_to(self):
        """So the mitigation can be run on the orchestration it was not written
        for. Without that, a multi-step arm beating a segmented one on a model
        that echoes schemas would be reporting the retry as a property of the
        pipeline."""
        client = MultiStepClient(detects=[SCHEMA_ECHO, {"entities": PLAN}])
        result = ExtractionAgent(
            client,
            arm("schema-dump-catalog-flat-enforced", CATALOGUE),
            profile_for("openai"),
            Orchestration.SEGMENTED,
            shortlist_k=2,
            plan_retry=True,
        ).run(request())
        assert result.selected == {"e1": ("Person",), "e2": ("Organization",)}

    @pytest.mark.parametrize(
        "orchestration",
        [Orchestration.SINGLE_SHOT, Orchestration.SELECT_THEN_FILL, Orchestration.SEGMENTED],
    )
    def test_only_multi_step_asks_again_unasked(self, orchestration):
        built = ExtractionAgent(
            MultiStepClient(), arm("schema-dump-catalog-flat-enforced", CATALOGUE), profile_for("openai"), orchestration
        )
        assert built.plan_retry is False

    def test_multi_step_asks_again_unasked(self):
        assert agent(MultiStepClient()).plan_retry is True


class TestWhatItShares:
    def test_a_missing_catalogue_is_refused(self):
        bare = ExtractionAgent(
            MultiStepClient(),
            arm("no-catalog-not-enforced"),
            profile_for("openai"),
            Orchestration.MULTI_STEP,
        )
        with pytest.raises(ValueError, match="needs a catalogue"):
            bare.run(request())

    def test_a_candidate_outside_the_catalogue_is_dropped(self):
        client = MultiStepClient(
            plan=[{"id": "e1", "candidates": ["Invented", "Person"], "mention": "Ada"}],
            fillable={"fillable": {"e1": ["name"]}},
            answers=[[{"id": "e1", "type": "Person"}]],
        )
        result = agent(client).run(request())
        assert result.selected == {"e1": ("Person",)}

    def test_a_request_without_ranges_says_nothing_about_links(self):
        client = MultiStepClient()
        agent(client).run(request(ranges=None))
        assert "points at" not in client.messages[2][0].content


class TestWhatTheDocumentCalledIt:
    """The mention the plan read, carried out of the whole run.

    ``identify`` returns it to a caller running one step. A caller running the
    orchestration had no way to the same answer, and it is the only one there
    is where the property step declines the slot that would hold the name:
    asked about "Jane works at ExampleCorp", claude-haiku-4-5 chooses
    ``worksFor`` and ``employee`` on 8 of 8 runs and ``name`` on none of them,
    which is defensible, since the sentence states an employment relation and
    not anybody's name.
    """

    def test_the_plan_step_mention_survives_the_run(self):
        client = MultiStepClient()
        result = agent(client).run(request())
        assert result.mentions == {"e1": "Ada", "e2": "Acme"}

    def test_it_survives_a_property_step_that_declines_the_name(self):
        client = MultiStepClient(
            fillable={"fillable": {"e1": ["worksFor"], "e2": []}},
            answers=[[{"id": "e1", "type": "Person", "worksFor": "e2"}], [{"id": "e2", "type": "Organization"}]],
        )
        result = agent(client).run(request())
        assert all("name" not in entity for entity in result.payload["entities"])
        assert result.mentions == {"e1": "Ada", "e2": "Acme"}

    def test_a_plan_placing_nothing_still_reports_what_it_read(self):
        client = MultiStepClient(plan=[{"id": "e1", "candidates": [], "mention": "Ada"}])
        result = agent(client).run(request())
        assert result.payload is None
        assert result.mentions == {"e1": "Ada"}

    def test_the_record_says_it(self):
        client = MultiStepClient()
        assert agent(client).run(request()).describe()["mentions"] == {"e1": "Ada", "e2": "Acme"}


class TestTheNameSlotAMentionKeeps:
    """The property step declines the name and the plan puts the slot back.

    The step is asked which properties the document states, and ``name`` loses
    that question even where the first clause answers it: over 60
    Wikidata-lead cells it is the most missed expected property, absent 59
    times. A mention is the plan saying the document calls the entity
    something, which is evidence the step's answer does not carry.

    The slot is kept, never filled. Which is the point of keeping it in the
    schema rather than writing the mention into the answer.
    """

    DECLINED = {"fillable": {"e1": ["worksFor"], "e2": []}}

    ANSWERS = [[{"id": "e1", "type": "Person", "worksFor": "e2"}], [{"id": "e2", "type": "Organization"}]]

    def sent(self, client=None, **kwargs):
        client = client or MultiStepClient(fillable=self.DECLINED, answers=self.ANSWERS)
        agent(client, **kwargs).run(request())
        return client

    def test_a_mention_keeps_the_slot_the_property_step_left_out(self):
        assert "name" in items_of(self.sent().formats[2])["properties"]

    def test_it_keeps_nothing_else_the_step_left_out(self):
        """Closing the property slot is what the arm is measuring, so the rule
        reaches one slot and the step still decides the rest."""
        offered = items_of(self.sent().formats[2])["properties"]
        assert "jobTitle" not in offered

    def test_the_result_names_the_entities_it_kept_it_for(self):
        """A slot that survives a declared enforcement axis against the step's
        answer is recorded rather than silent."""
        result = agent(MultiStepClient(fillable=self.DECLINED, answers=self.ANSWERS)).run(request())
        assert result.named == ["e1", "e2"]

    def test_the_property_step_s_own_answer_is_reported_as_it_came(self):
        """The complement of the record above. A name in one was the step's
        answer, a key in the other was the plan's, and folding the two would
        report the step as having chosen what it declined."""
        result = agent(MultiStepClient(fillable=self.DECLINED, answers=self.ANSWERS)).run(request())
        assert result.properties_chosen == {"e1": ("worksFor",), "e2": ()}

    def test_an_entity_that_chose_the_name_itself_is_not_named_by_the_rule(self):
        assert agent(MultiStepClient()).run(request()).named == []

    def test_the_plan_reading_no_mention_keeps_nothing(self):
        """An orchestration with no plan step has nothing to justify it, and
        neither has a plan entry that designates nothing."""
        client = MultiStepClient(
            plan=[{"id": "e1", "candidates": ["Person"], "mention": ""}],
            fillable={"fillable": {"e1": ["worksFor"]}},
            answers=[[{"id": "e1", "type": "Person", "worksFor": "e2"}]],
        )
        result = agent(client).run(request())
        assert "name" not in items_of(client.formats[2])["properties"]
        assert result.named == []

    def test_a_shortlist_that_admits_no_name_keeps_nothing(self):
        """For the reason the property step drops a name the entity cannot
        carry: the slot would be one no class on the shortlist declares."""
        client = MultiStepClient(fillable={"fillable": {"e1": ["worksFor"], "e2": ["legalName"]}})
        result = agent(client).run(replace(request(), parents=None))
        assert result.named == []

    def test_the_rule_adds_nothing_to_the_required_list(self):
        """The slot is kept, not demanded. "Jane works at ExampleCorp" states
        an employment relation and not that Jane's name is Jane, and a model
        declining the slot is right."""
        assert "name" not in items_of(self.sent(profile="anthropic").formats[2])["required"]

    def test_a_subset_that_requires_everything_still_leaves_it_declinable(self):
        """Where the profile rewrites `required` from `properties`, null is
        how a model declines, and the kept slot is no worse off than one the
        step chose."""
        assert "null" in items_of(self.sent().formats[2])["properties"]["name"]["type"]

    def test_an_answer_that_declines_it_is_kept_as_it_came(self):
        result = agent(MultiStepClient(fillable=self.DECLINED, answers=self.ANSWERS)).run(request())
        assert all("name" not in entity for entity in result.payload["entities"])

    def test_the_prompt_names_it_among_the_properties_to_fill(self):
        """Named as every kept property is, because an arm that shows no
        schema still has to be told the slot is there."""
        assert "Report only these properties for them: name, worksFor." in self.sent().messages[2][0].content

    def test_two_entities_the_rule_separates_do_not_share_a_call(self):
        """Entities sharing a call share the schema that call is sent, so the
        kept slot splits a group the step alone would have pooled."""
        client = MultiStepClient(
            plan=[
                {"id": "e1", "candidates": ["Person"], "mention": "Ada"},
                {"id": "e2", "candidates": ["Person"], "mention": ""},
            ],
            fillable={"fillable": {"e1": ["jobTitle"], "e2": ["jobTitle"]}},
            answers=[[{"id": "e1", "type": "Person"}], [{"id": "e2", "type": "Person"}]],
        )
        agent(client).run(request())
        assert client.calls == 4

    def test_the_record_is_serialisable(self):
        described = agent(MultiStepClient(fillable=self.DECLINED, answers=self.ANSWERS)).run(request()).describe()
        assert json.dumps(described)
        assert described["named"] == ["e1", "e2"]


class TestAskingForWhatTheDocumentDoesNotSay:
    """A required property the property step left out is a question, not a guess."""

    @staticmethod
    def _schema_requiring(name):
        return {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "id": {"type": "string"},
                            "value": {"type": "number"},
                            name: {"type": "string"},
                        },
                        "required": ["type", name],
                    },
                }
            },
        }

    def test_an_unfillable_required_property_is_asked_for_and_left_out(self):
        """Inventing a value is the one answer that is always wrong.

        Under a strict grammar over a subset that makes every property
        required, the model has no way to decline, so the agent has to decline
        on its behalf. Left out of the fill schema is the honest shape of
        "this document does not say".
        """
        client = MultiStepClient()
        built = agent(client)
        built.run(replace(request(), schema=self._schema_requiring("serial")))

        assert [a["property"] for a in built.asked] == ["serial"] * len(built.asked)
        assert built.asked, "a required property the property step omitted was never asked for"
        assert "serial" not in json.dumps(client.formats[-1])

    def test_an_answered_question_puts_the_property_back(self):
        """A caller that can supply it gets it filled rather than dropped.

        A benchmark answers mechanically from the corpus and a playground asks
        the person in front of it; the agent only has to ask.
        """
        client = MultiStepClient()
        built = agent(client, information=lambda key, name: "SN-1")
        built.run(replace(request(), schema=self._schema_requiring("serial")))

        assert built.asked
        assert "serial" in json.dumps(client.formats[-1])
        assert built.supplied and all("serial" in v for v in built.supplied.values())

    def test_nothing_is_asked_when_the_document_fills_what_is_required(self):
        """`name` is in the fixture's fillable set, so there is no question."""
        client = MultiStepClient()
        built = agent(client)
        built.run(replace(request(), schema=self._schema_requiring("name")))
        assert built.asked == []


class TestEachStepAlone:
    """A pipeline whose steps cannot be run apart cannot be attributed.

    The four steps already exist inside the orchestrations. These are the
    public doors onto them, so a benchmark can hand one step known-correct
    input and score it on its own question rather than on the one before it.
    """

    def test_identify_returns_the_shortlist_and_the_mention(self):
        client = MultiStepClient()
        selected, mentions = agent(client).identify(request())
        assert selected == {"e1": ("Person",), "e2": ("Organization",)}
        assert mentions == {"e1": "Ada", "e2": "Acme"}
        assert client.calls == 1, "identify is one call and nothing after it"

    def test_identify_does_not_carry_a_mention_between_documents(self):
        """An agent reused across documents would otherwise answer with a
        mention read from the one before."""
        one = agent(MultiStepClient())
        one.identify(request())
        one.client = MultiStepClient(
            detects=[{"entities": [{"id": "e9", "candidates": ["Book"], "mention": "Ulysses"}]}]
        )
        _, mentions = one.identify(request())
        assert mentions == {"e9": "Ulysses"}

    def test_fillable_properties_takes_the_plan_it_is_given(self):
        client = MultiStepClient(detects=[])
        plan = (
            PlannedEntity(key="e1", classes=("Person",), mention="Ada"),
            PlannedEntity(key="e2", classes=("Organization",), mention="Acme"),
        )
        assert agent(client).fillable_properties(request(), plan) == {"e1": ("name", "worksFor"), "e2": ("name",)}

    def test_available_properties_is_what_the_step_may_choose_from(self):
        """The union over the shortlist, so a step scored on its choice is
        scored against what it was actually offered."""
        plan = (PlannedEntity(key="e1", classes=("Person",), mention="Ada"),)
        available = agent(MultiStepClient()).available_properties(request(), plan)
        assert set(available["e1"]) == {"name", "jobTitle", "worksFor"}

    def test_extract_pins_the_id_to_the_entities_the_call_is_for(self):
        """Without this the answer cannot be joined back to the plan, and
        every edge reads as dangling."""
        client = MultiStepClient(detects=[])
        plan = (
            PlannedEntity(key="e1", classes=("Person",), mention="Ada"),
            PlannedEntity(key="e2", classes=("Organization",), mention="Acme"),
        )
        agent(client).extract(request(), plan=plan, filling=("e1",))
        assert _id_slot(client.formats[-1])["enum"] == ["e1"]

    def test_extract_without_a_plan_is_the_single_shot_arm(self):
        client = MultiStepClient(detects=[])
        result = agent(client).extract(request())
        assert result.payload is not None
        assert _id_slot(client.formats[-1]) is None


def _id_slot(schema):
    """The id property of whichever entity shape the request carried."""
    if not isinstance(schema, dict):
        return None
    if "id" in (schema.get("properties") or {}) and schema.get("type") == "object":
        return schema["properties"]["id"]
    for value in list((schema.get("properties") or {}).values()) + schema.get("anyOf", []) + [schema.get("items")]:
        found = _id_slot(value)
        if found is not None:
            return found
    return None


class TestReadingTheAnswer:
    """Names alone, and an answer that carries more is still read.

    A quotation was required for a while, to make the step point at the text.
    It did not reduce invention and it cost the cautious models their recall,
    so the schema asks for names; the reader stays tolerant because a model
    may volunteer more than it was asked for.
    """

    def test_the_answer_is_names_alone(self):
        from oold.agent.prompts import property_schema

        item = property_schema({"e1": ("name",)})["properties"]["fillable"]["properties"]["e1"]["items"]
        assert item == {"type": "string", "enum": ["name"]}

    def test_an_answer_carrying_a_quotation_is_still_read(self):
        client = MultiStepClient(detects=[])
        plan = (PlannedEntity(key="e1", classes=("Person",), mention="Ada"),)
        assert agent(client).fillable_properties(request(), plan) == {"e1": ("name", "worksFor")}

    def test_a_bare_name_is_still_read(self):
        """A model answering the older shape has answered the question."""
        client = MultiStepClient(detects=[], fillable={"fillable": {"e1": ["name"]}})
        plan = (PlannedEntity(key="e1", classes=("Person",), mention="Ada"),)
        assert agent(client).fillable_properties(request(), plan) == {"e1": ("name",)}

    def test_an_item_naming_no_property_is_dropped(self):
        client = MultiStepClient(detects=[], fillable={"fillable": {"e1": [{"stated": "Ada"}]}})
        plan = (PlannedEntity(key="e1", classes=("Person",), mention="Ada"),)
        assert agent(client).fillable_properties(request(), plan) == {"e1": ()}


class TestAskingForTheWordsThatStateIt:
    """Off by default, because it costs more than it buys.

    What a model writes there says what it thought it was reading, which is
    worth being able to ask for even though requiring it lowers the score.
    """

    def test_the_default_answer_is_names_alone(self):
        from oold.agent.prompts import property_schema

        assert property_schema({"e1": ("name",)})["properties"]["fillable"]["properties"]["e1"]["items"] == {
            "type": "string",
            "enum": ["name"],
        }

    def test_asked_for_it_the_answer_carries_both(self):
        from oold.agent.prompts import property_schema

        item = property_schema({"e1": ("name",)}, evidence=True)["properties"]["fillable"]["properties"]["e1"]["items"]
        assert item["required"] == ["property", "stated"]
        assert item["properties"]["property"]["enum"] == ["name"]

    def test_the_request_decides(self):
        client = MultiStepClient(detects=[])
        plan = (PlannedEntity(key="e1", classes=("Person",), mention="Ada"),)
        agent(client).fillable_properties(request(), plan)
        assert client.formats[-1]["properties"]["fillable"]["properties"]["e1"]["items"]["type"] == "string"

    def test_what_the_model_wrote_is_kept_for_the_caller(self):
        """The answer is the names; this is the working behind them."""
        client = MultiStepClient(detects=[])
        plan = (PlannedEntity(key="e1", classes=("Person",), mention="Ada"),)
        one = agent(client)
        one.fillable_properties(request(), plan)
        assert one.fillable_answer["e1"][0] == {"property": "name", "stated": "Ada"}


class TestACallReportsOnlyWhatItWasAskedFor:
    """A grouped call is told which ids it fills and which others exist.

    The others are named so an edge has a name to point at. A model reads
    both lists and sometimes reports both, and the entity then arrives twice:
    once from the call that owns it, once from a call that was only told
    about it. Two entities in the answer where the document holds one.
    """

    def test_an_entity_another_call_owns_is_dropped(self):
        from oold.agent.extraction import _owned_by

        answered = [
            {"id": "e5", "type": "Recipe", "name": "Pancakes"},
            {"id": "e1", "type": "Person", "name": "Andrea"},
        ]
        assert _owned_by(answered, ["e5", "e6"]) == [answered[0]]

    def test_an_entity_with_no_id_is_kept(self):
        """No call can claim it, so dropping it in every group loses it."""
        from oold.agent.extraction import _owned_by

        answered = [{"type": "Recipe", "name": "Pancakes"}]
        assert _owned_by(answered, ["e5"]) == answered

    def test_the_id_is_read_under_any_of_the_names_an_answer_uses(self):
        from oold.agent.extraction import _owned_by

        assert _owned_by([{"@id": "e9", "type": "Review"}], ["e5"]) == []
        assert _owned_by([{"entity_id": "e5", "type": "Review"}], ["e5"]) != []


class TestAnEmbeddedEntityIsConstrainedToo:
    """A schema may put an entity where a value goes.

    That is how a value object is written: the address belongs to the person
    and is serialised inside it. It carries an id and may point at others, so
    it needs the same two constraints the top-level shape gets, or its id is
    one the plan never issued and nothing can be joined to it.
    """

    def _schema(self):
        return {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "address": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "id": {"type": "string"},
                                        "streetAddress": {"type": "string"},
                                    },
                                },
                            },
                        },
                    },
                }
            },
        }

    def test_the_walk_reaches_the_entity_inside_the_entity(self):
        from oold.agent.extraction import _entity_shapes

        shapes = _entity_shapes(self._schema())
        assert [sorted(shape["properties"]) for shape in shapes] == [
            ["address", "id", "name", "type"],
            ["id", "streetAddress", "type"],
        ]

    def test_the_holder_is_found_before_the_entity_it_holds(self):
        """So an embedded entity is pinned after it and never instead of it."""
        from oold.agent.extraction import _entity_shapes

        shapes = _entity_shapes(self._schema())
        assert "address" in shapes[0]["properties"]

    def test_a_schema_that_nests_nothing_is_unchanged(self):
        from oold.agent.extraction import _entity_shapes

        flat = {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"type": {"type": "string"}, "name": {"type": "string"}}},
                }
            },
        }
        assert len(_entity_shapes(flat)) == 1
