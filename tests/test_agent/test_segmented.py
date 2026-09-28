"""Plan the whole document, then fill the plan.

The orchestration exists because an edge belongs to no single entity. Every
arm before it answers one entity's own values, so the call that holds a link
never learns that the entity at the other end has a name, and the link can
only be written as prose or dropped. Planning first gives both ends a name
both steps agree on, and pinning the reference slot to those names is the only
place anywhere that a link is constrained to a real target.
"""

import json

import pytest

from oold.agent.client import ChatResponse, TokenUsage
from oold.agent.enforcement import Orchestration, arm
from oold.agent.extraction import Edge, ExtractionAgent, PlannedEntity
from oold.agent.prompts import ExtractionRequest
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

LINKED = [
    [{"id": "e1", "type": "Person", "name": "Ada", "worksFor": "e2"}],
    [{"id": "e2", "type": "Organization", "name": "Acme"}],
]

UNION_PLAN = [
    {"id": "e1", "candidates": ["Person", "Book"], "mention": "Ada"},
    {"id": "e2", "candidates": ["Organization", "LocalBusiness"], "mention": "Acme"},
]
"""Two classes per entity, so every fill call is sent a union of two branches
and a profile that refuses ``anyOf`` has something to lose. A shortlist of one
flattens to a wider object than it came from, and the loss that matters is
invisible in the keyword count."""


class PlanThenFillClient:
    """Answers the plan step, then one fill step per shortlist."""

    model = "planner"

    def __init__(self, plan=None, answers=None) -> None:
        self.plan = list(PLAN if plan is None else plan)
        self.answers = [list(group) for group in (LINKED if answers is None else answers)]
        self.formats: list = []
        self.messages: list = []
        self.calls = 0

    def invoke(self, messages, *, response_format=None) -> ChatResponse:
        self.calls += 1
        self.formats.append(response_format)
        self.messages.append(list(messages))
        if self.calls == 1:
            payload = {"entities": self.plan}
        else:
            payload = {"entities": self.answers.pop(0) if self.answers else []}
        return ChatResponse(
            text=json.dumps(payload),
            parsed=None,
            usage=TokenUsage(input_tokens=100, output_tokens=10),
        )


def agent(client, name="A2", profile="openai", k=2):
    return ExtractionAgent(
        client,
        arm(name, CATALOGUE),
        profile_for(profile),
        Orchestration.SEGMENTED,
        shortlist_k=k,
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
    """The entity shape a fill call was sent, union or object."""
    return response_format["properties"]["entities"]["items"]


def targets_of(slot):
    """The ids a pinned slot offers, without the null that lets it decline."""
    return [value for value in slot["enum"] if value is not None]


class TestTheCallsItMakes:
    def test_one_plan_call_and_one_fill_call_per_shortlist(self):
        client = PlanThenFillClient()
        agent(client).run(request())
        assert client.calls == 3

    def test_the_steps_are_named_apart_in_the_log(self):
        """Per-step tokens are the only way to cost the orchestration, and
        pooling the plan under the name select-then-fill uses would make two
        orchestrations indistinguishable in the same results table."""
        result = agent(PlanThenFillClient()).run(request())
        assert [c["step"] for c in result.calls.describe()["calls"]] == ["plan", "fill", "fill"]

    def test_tokens_are_attributed_to_the_step_that_spent_them(self):
        result = agent(PlanThenFillClient()).run(request())
        by_step = result.calls.by_step()
        assert by_step["plan"].input_tokens == 100
        assert by_step["fill"].input_tokens == 200

    def test_entities_that_shortlist_the_same_classes_share_a_fill_call(self):
        client = PlanThenFillClient(
            plan=[
                {"id": "e1", "candidates": ["Person"], "mention": "Ada"},
                {"id": "e2", "candidates": ["Person"], "mention": "Grace"},
            ],
            answers=[[{"id": "e1", "type": "Person"}, {"id": "e2", "type": "Person"}]],
        )
        agent(client).run(request())
        assert client.calls == 2

    def test_the_plan_step_asks_the_selection_question(self):
        client = PlanThenFillClient()
        agent(client).run(request())
        assert client.formats[0]["title"] == "EntityCandidates"

    def test_the_shortlist_is_recorded_per_entity(self):
        """So a two-step failure stays attributable to a step."""
        result = agent(PlanThenFillClient()).run(request())
        assert result.selected == {"e1": ("Person",), "e2": ("Organization",)}

    def test_a_plan_that_placed_nothing_stops_before_the_fill_call(self):
        client = PlanThenFillClient(plan=[{"id": "e1", "candidates": [], "mention": "Ada"}])
        result = agent(client).run(request())
        assert client.calls == 1
        assert result.payload is None
        assert result.selected == {"e1": ()}


class TestWhatTheFillStepIsGiven:
    def sent(self, client=None):
        client = client or PlanThenFillClient()
        agent(client).run(request())
        return client

    def test_the_fill_step_sees_the_whole_document_again(self):
        """A plan summary would be a bottleneck the grader cannot see past:
        an entity lost there would read as an extraction failure."""
        assert self.sent().messages[1][1].content == DOCUMENT

    def test_the_fill_prompt_names_the_entities_it_is_for_by_id(self):
        content = self.sent().messages[1][0].content
        assert 'e1 ("Ada")' in content

    def test_the_fill_prompt_names_the_entities_another_call_fills(self):
        """A source and a target that shortlisted different classes are filled
        by different calls, and the one holding the source cannot state the
        edge unless it knows the target has a name."""
        content = self.sent().messages[1][0].content
        assert 'e2 ("Acme")' in content
        assert "also describes" in content

    def test_the_ids_are_named_even_when_one_call_covers_the_plan(self):
        """Where this parts company with select-then-fill, which sends the
        unchanged instruction for a single group because the id is only an
        internal label there."""
        client = PlanThenFillClient(
            plan=[{"id": "e1", "candidates": ["Person"], "mention": "Ada"}],
            answers=[[{"id": "e1", "type": "Person"}]],
        )
        agent(client).run(request())
        assert 'e1 ("Ada")' in client.messages[1][0].content

    def test_a_request_without_ranges_says_nothing_about_links(self):
        client = PlanThenFillClient()
        ExtractionAgent(
            client,
            arm("A2", CATALOGUE),
            profile_for("openai"),
            Orchestration.SEGMENTED,
            shortlist_k=2,
        ).run(request(ranges=None))
        assert "points at" not in client.messages[1][0].content


class TestTheIdSlot:
    def sent(self, client=None):
        client = client or PlanThenFillClient()
        agent(client).run(request())
        return client

    def test_the_answer_shape_carries_a_slot_for_the_planned_id(self):
        """An id the model states is what makes two mentions being one entity
        a question the model is asked. Attached afterwards by position, as the
        predecessor did, it never is."""
        assert "id" in items_of(self.sent().formats[1])["properties"]

    def test_a_fill_call_is_pinned_to_the_ids_it_is_for(self):
        """Offering every planned id would let one call emit an entity another
        call is responsible for, and it would be counted twice."""
        client = self.sent()
        assert items_of(client.formats[1])["properties"]["id"]["enum"] == ["e1"]
        assert items_of(client.formats[2])["properties"]["id"]["enum"] == ["e2"]

    def test_the_id_is_required(self):
        assert "id" in items_of(self.sent().formats[1])["required"]


class TestPinningAReference:
    def sent(self, client=None):
        client = client or PlanThenFillClient()
        agent(client).run(request())
        return client

    def test_only_a_compatible_entity_is_offered(self):
        """The only place anywhere that a link is constrained to a real
        target."""
        assert targets_of(items_of(self.sent().formats[1])["properties"]["worksFor"]) == ["e2"]

    def test_an_entity_whose_class_is_not_in_the_range_is_absent(self):
        """Ada is a Person and worksFor ranges over Organization, so pinning
        the slot to her id would make the wrong edge the only legal one."""
        assert "e1" not in targets_of(items_of(self.sent().formats[1])["properties"]["worksFor"])

    def test_a_subclass_of_the_range_is_offered(self):
        plan = (
            PlannedEntity(key="e1", classes=("Person",)),
            PlannedEntity(key="e2", classes=("LocalBusiness",)),
        )
        pinned, _ = agent(PlanThenFillClient())._pin_references(
            {"properties": {"type": {}, "worksFor": {"type": "object"}}},
            plan,
            {"worksFor": ("Organization",)},
            PARENTS,
        )
        assert pinned["properties"]["worksFor"]["enum"] == ["e2"]

    def test_a_shortlist_counts_when_any_class_on_it_fits(self):
        """The fill step has not committed to one yet, and offering only the
        first would rule out a target the second call may well answer with."""
        plan = (PlannedEntity(key="e1", classes=("Book", "Organization")),)
        pinned, _ = agent(PlanThenFillClient())._pin_references(
            {"properties": {"type": {}, "worksFor": {"type": "object"}}},
            plan,
            {"worksFor": ("Organization",)},
            PARENTS,
        )
        assert pinned["properties"]["worksFor"]["enum"] == ["e1"]

    def test_a_nullable_slot_keeps_a_way_of_declining(self):
        """A subset that makes every property required leaves null as the only
        way to say nothing. A pinned slot that dropped it would force an edge
        out of every entity that has the slot."""
        plan = (PlannedEntity(key="e2", classes=("Organization",)),)
        pinned, _ = agent(PlanThenFillClient())._pin_references(
            {"properties": {"type": {}, "worksFor": {"type": ["object", "null"]}}},
            plan,
            {"worksFor": ("Organization",)},
            PARENTS,
        )
        assert pinned["properties"]["worksFor"]["type"] == ["string", "null"]
        assert None in pinned["properties"]["worksFor"]["enum"]

    def test_a_range_no_planned_entity_fits_is_left_open(self):
        """An empty enum is not a tighter constraint but an unsatisfiable one,
        so the slot stays as the schema declares it."""
        plan = (PlannedEntity(key="e1", classes=("Person",)),)
        schema = {"properties": {"type": {}, "worksFor": {"type": "object"}}}
        pinned, unpinned = agent(PlanThenFillClient())._pin_references(
            schema, plan, {"worksFor": ("Organization",)}, PARENTS
        )
        assert pinned["properties"]["worksFor"] == {"type": "object"}
        assert unpinned == ["worksFor"]

    def test_leaving_a_slot_open_is_recorded_on_the_result(self):
        """An arm that ran unconstrained on a slot and never said so would be
        reported as a finding about constrained links."""
        client = PlanThenFillClient(
            plan=[{"id": "e1", "candidates": ["Person"], "mention": "Ada"}],
            answers=[[{"id": "e1", "type": "Person"}]],
        )
        result = agent(client).run(request())
        assert result.unpinned == ["worksFor"]

    def test_a_property_the_schema_does_not_carry_is_passed_over(self):
        """A catalogue trim upstream or a provider's optional-property limit
        can lose a slot legitimately, and a slot that is not offered is not a
        slot left open."""
        plan = (PlannedEntity(key="e2", classes=("Organization",)),)
        _, unpinned = agent(PlanThenFillClient())._pin_references(
            {"properties": {"type": {}}}, plan, {"worksFor": ("Organization",)}, PARENTS
        )
        assert unpinned == []

    def test_a_schema_with_no_entity_shape_is_refused(self):
        plan = (PlannedEntity(key="e1", classes=("Person",)),)
        with pytest.raises(ValueError, match="no entity shape"):
            agent(PlanThenFillClient())._pin_references(
                {"properties": {"headline": {"type": "string"}}}, plan, RANGES, PARENTS
            )

    def test_an_unconstrained_arm_pins_no_reference(self):
        """The decode axis keeps meaning what it means everywhere else."""
        client = PlanThenFillClient()
        agent(client, name="A1").run(request())
        assert client.formats[1] is None


class TestTheLinkSurvives:
    def test_the_payload_carries_the_link(self):
        result = agent(PlanThenFillClient()).run(request())
        by_id = {entity["id"]: entity for entity in result.payload["entities"]}
        assert by_id["e1"]["worksFor"] == "e2"

    def test_every_planned_entity_is_merged_into_one_answer(self):
        result = agent(PlanThenFillClient()).run(request())
        assert sorted(e["id"] for e in result.payload["entities"]) == ["e1", "e2"]

    def test_the_link_is_recorded_as_an_edge(self):
        result = agent(PlanThenFillClient()).run(request())
        assert result.links == [Edge(source="e1", prop="worksFor", target="e2")]

    def test_a_resolved_link_is_not_dangling(self):
        assert agent(PlanThenFillClient()).run(request()).dangling == []

    def test_the_record_is_serialisable(self):
        described = agent(PlanThenFillClient()).run(request()).describe()
        assert json.dumps(described)
        assert described["links"] == [{"source": "e1", "prop": "worksFor", "target": "e2"}]


class TestADanglingReference:
    """A plan that names a target the fill step then fails to emit.

    A real outcome and not a bug to paper over: the edge is kept and flagged,
    because an answer pointing at an entity it never reported is a different
    failure from an answer reporting no edge, and dropping it would make the
    two the same number.
    """

    def run(self):
        client = PlanThenFillClient(answers=[LINKED[0], []])
        return agent(client).run(request())

    def test_the_edge_is_recorded_as_dangling(self):
        assert self.run().dangling == [Edge(source="e1", prop="worksFor", target="e2")]

    def test_the_edge_stays_in_the_payload(self):
        assert self.run().payload["entities"][0]["worksFor"] == "e2"

    def test_it_is_still_counted_among_the_links(self):
        result = self.run()
        assert result.links == result.dangling


class TestWhatEachProviderGets:
    """The pinned schema under two subsets, with the fidelity reported.

    Pinning happens after the provider transform, as it does for the class and
    the unit enum, so the fidelity figure is the transform's and says nothing
    about the pin. What it does say is that the same condition costs different
    amounts on different providers, which is why cells of differing fidelity
    are never averaged.
    """

    def sent(self, profile):
        client = PlanThenFillClient(
            plan=UNION_PLAN,
            answers=[[{"id": "e1", "type": "Person", "worksFor": "e2"}], [{"id": "e2", "type": "Organization"}]],
        )
        result = agent(client, name="A4", profile=profile).run(request())
        return items_of(client.formats[1]), result.degradation

    def test_a_profile_that_takes_anyof_keeps_the_union_and_the_pin(self):
        items, degradation = self.sent("openai")
        branch = next(b for b in items["anyOf"] if "worksFor" in b["properties"])
        assert targets_of(branch["properties"]["worksFor"]) == ["e2"]
        assert degradation.dropped.get("anyOf") is None

    def test_the_pinned_id_reaches_every_branch(self):
        """Pinning the first branch alone would constrain one class and leave
        the others open, which reads as a finding about that class."""
        items, _ = self.sent("openai")
        assert all(targets_of(branch["properties"]["id"]) == ["e1"] for branch in items["anyOf"])

    def test_a_profile_that_refuses_anyof_still_gets_the_pin(self):
        items, _ = self.sent("anthropic")
        assert "anyOf" not in items
        assert targets_of(items["properties"]["worksFor"]) == ["e2"]

    def test_refusing_anyof_is_recorded_as_a_loss(self):
        """Reporting fidelity 1.000 here is the bug this test exists for."""
        _, degradation = self.sent("anthropic")
        assert degradation.dropped.get("anyOf") == 1
        assert degradation.fidelity < 1.0

    def test_the_fidelity_reported_is_the_last_fill_call_s(self):
        """As it is for select-then-fill. A two-step arm sends one schema per
        shortlist and the record holds one figure, so a plan whose groups
        differ in fidelity is reported by its last group and not by its worst.
        """
        _, degradation = self.sent("anthropic")
        assert degradation.keywords_before > 0

    def test_the_two_profiles_report_different_fidelity(self):
        _, keeps = self.sent("openai")
        _, loses = self.sent("anthropic")
        assert loses.fidelity < keeps.fidelity


class TestWhatItShares:
    def test_a_missing_catalogue_is_refused(self):
        bare = ExtractionAgent(
            PlanThenFillClient(),
            arm("A0-json"),
            profile_for("openai"),
            Orchestration.SEGMENTED,
        )
        with pytest.raises(ValueError, match="needs a catalogue"):
            bare.run(request())

    def test_a_candidate_outside_the_catalogue_is_dropped(self):
        client = PlanThenFillClient(
            plan=[{"id": "e1", "candidates": ["Invented", "Person"], "mention": "Ada"}],
            answers=[[{"id": "e1", "type": "Person"}]],
        )
        result = agent(client).run(request())
        assert result.selected == {"e1": ("Person",)}
