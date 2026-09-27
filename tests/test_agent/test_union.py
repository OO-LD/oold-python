"""The discriminated union, and what a provider that refuses it gets instead.

The degradation test is the important one. A union that collapses to its first
branch is not a degraded schema, it is a wrong one: a hundred-class union
becomes one class, the model can only answer that class, and the run reads as
a finding about the model.
"""

import json

import pytest

from oold.agent.client import ChatResponse
from oold.agent.enforcement import arm
from oold.agent.extraction import ExtractionAgent
from oold.agent.prompts import ExtractionRequest
from oold.agent.provider import prepare, profile_for
from oold.agent.union import branch_for, flatten_union, nested_union, union_schema

BRANCHES = {
    "Length": {"unit": {"type": "string", "enum": ["meter", "kilo_meter"]}},
    "Mass": {"unit": {"type": "string", "enum": ["gram", "kilo_gram"]}},
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


class RecordingClient:
    model = "recorder"

    def __init__(self) -> None:
        self.response_format = None

    def invoke(self, messages, *, response_format=None) -> ChatResponse:
        self.response_format = response_format
        return ChatResponse(text='{"entities": []}', parsed=None)


class TestBuildingTheUnion:
    def test_one_branch_per_class(self):
        assert len(union_schema(BRANCHES)["anyOf"]) == 3

    def test_each_branch_pins_its_own_class(self):
        built = union_schema(BRANCHES)["anyOf"]
        assert [b["properties"]["type"]["const"] for b in built] == ["Length", "Mass", "Volume"]

    def test_each_branch_carries_only_its_own_values(self):
        built = union_schema(BRANCHES)["anyOf"]
        assert built[0]["properties"]["unit"]["enum"] == ["meter", "kilo_meter"]
        assert built[2]["properties"]["unit"]["enum"] == ["liter"]

    def test_the_discriminator_is_always_required(self):
        """A branch nobody has to discriminate is a branch that matches anything."""
        assert "type" in union_schema(BRANCHES)["anyOf"][0]["required"]

    def test_shared_properties_reach_every_branch(self):
        built = union_schema(BRANCHES, shared={"value": {"type": "number"}})["anyOf"]
        assert all("value" in b["properties"] for b in built)

    def test_a_branch_narrowing_wins_over_the_shared_part(self):
        built = union_schema(BRANCHES, shared={"unit": {"type": "string"}})["anyOf"]
        assert built[0]["properties"]["unit"]["enum"] == ["meter", "kilo_meter"]

    def test_an_empty_union_is_refused(self):
        """Nothing satisfies it, so a model could only fail."""
        with pytest.raises(ValueError, match="at least one branch"):
            union_schema({})

    def test_a_single_branch_is_still_a_union(self):
        assert len(union_schema({"Length": BRANCHES["Length"]})["anyOf"]) == 1

    def test_branch_for_builds_one_branch(self):
        built = branch_for("Length", {"unit": {"enum": ["meter"]}}, required=("unit",))
        assert built["properties"]["type"]["const"] == "Length"
        assert set(built["required"]) == {"type", "unit"}


class TestFlatteningTheUnion:
    def test_every_class_survives(self):
        """The bug this exists for: keeping branch 0 loses every other class."""
        flat = flatten_union(union_schema(BRANCHES))
        assert flat["properties"]["type"]["enum"] == ["Length", "Mass", "Volume"]

    def test_every_value_survives(self):
        flat = flatten_union(union_schema(BRANCHES))
        assert flat["properties"]["unit"]["enum"] == [
            "meter",
            "kilo_meter",
            "gram",
            "kilo_gram",
            "liter",
        ]

    def test_the_pairing_is_what_is_lost(self):
        """Length with gram is now admissible. That is the degradation."""
        flat = flatten_union(union_schema(BRANCHES))
        assert "gram" in flat["properties"]["unit"]["enum"]
        assert "anyOf" not in flat

    def test_something_that_is_not_a_union_is_left_alone(self):
        assert flatten_union({"type": "object"}) == {"type": "object"}


class TestWhatEachProviderGets:
    def test_a_provider_that_takes_anyof_keeps_the_union(self):
        prepared, degradation = prepare(union_schema(BRANCHES), profile_for("openai"))
        assert "anyOf" in prepared
        assert len(prepared["anyOf"]) == 3
        assert degradation.dropped.get("anyOf") is None

    def test_a_provider_that_refuses_anyof_keeps_every_class(self):
        prepared, _ = prepare(union_schema(BRANCHES), profile_for("anthropic"))
        assert "anyOf" not in prepared
        assert prepared["properties"]["type"]["enum"] == ["Length", "Mass", "Volume"]

    def test_refusing_anyof_is_recorded_as_a_loss(self):
        _, degradation = prepare(union_schema(BRANCHES), profile_for("anthropic"))
        assert degradation.dropped.get("anyOf") == 1
        assert degradation.fidelity < 1.0

    def test_the_same_union_costs_more_on_one_provider_than_another(self):
        """The first condition where the provider profile changes the
        treatment. Cells of differing fidelity are never averaged."""
        union = union_schema(BRANCHES)
        _, keeps = prepare(union, profile_for("openai"))
        _, loses = prepare(union, profile_for("anthropic"))
        assert loses.fidelity < keeps.fidelity

    def test_a_flat_schema_costs_no_combinator_on_any_profile(self):
        """Which is why every run so far reported no combinator loss."""
        for name in ("openai", "anthropic", "google", "native"):
            _, degradation = prepare(SCHEMA, profile_for(name))
            assert degradation.dropped.get("anyOf") is None


class TestTheUnionArm:
    def sent(self, name, branches=BRANCHES, catalogue=("Length", "Mass")):
        client = RecordingClient()
        ExtractionAgent(client, arm(name, catalogue), profile_for("openai")).run(
            ExtractionRequest(document="d", schema=SCHEMA, branches=branches)
        )
        return client.response_format

    def test_a4_sends_a_union_over_the_offered_classes(self):
        items = self.sent("A4")["properties"]["entities"]["items"]
        assert [b["properties"]["type"]["const"] for b in items["anyOf"]] == ["Length", "Mass"]

    def test_a4_pairs_each_class_with_its_own_units(self):
        items = self.sent("A4")["properties"]["entities"]["items"]
        by_class = {b["properties"]["type"]["const"]: b["properties"]["unit"]["enum"] for b in items["anyOf"]}
        assert by_class == {"Length": ["meter", "kilo_meter"], "Mass": ["gram", "kilo_gram"]}

    def test_a2_cannot_express_the_pairing(self):
        items = self.sent("A2")["properties"]["entities"]["items"]
        assert "anyOf" not in items
        assert items["properties"]["type"]["enum"] == ["Length", "Mass"]

    def test_a_class_outside_the_catalogue_is_not_offered(self):
        items = self.sent("A4")["properties"]["entities"]["items"]
        assert "Volume" not in [b["properties"]["type"]["const"] for b in items["anyOf"]]

    def test_a_union_arm_without_branches_fails_loudly(self):
        """Running unconstrained would be reported as a finding about unions."""
        with pytest.raises(ValueError, match="carried none"):
            self.sent("A4", branches=None)

    def test_a_union_arm_whose_classes_have_no_branch_fails_loudly(self):
        with pytest.raises(ValueError, match="admit nothing"):
            self.sent("A4", catalogue=("Nonesuch",))


class TestTheEnforcedOnlyArm:
    def test_it_sends_the_schema_without_showing_it(self):
        """The enum reaches the decoder and not the prompt, so reading it and
        being constrained by it stop being the same condition."""
        client = RecordingClient()
        agent = ExtractionAgent(client, arm("A2-enforced-only", ("Length", "Mass")), profile_for("openai"))
        from oold.agent.prompts import build_messages

        request = ExtractionRequest(document="d", schema=SCHEMA, branches=BRANCHES)
        agent.run(request)
        assert client.response_format is not None
        messages = build_messages(ExtractionRequest(document="d", schema=None), agent.enforcement)
        assert "Each entity must conform" not in messages[0].content

    def test_it_still_offers_the_catalogue(self):
        from oold.agent.prompts import build_messages

        content = build_messages(ExtractionRequest(document="d"), arm("A2-enforced-only", ("Length",)))[0].content
        assert "- Length" in content


class TestTheUnionReachesTheProviderTransform:
    """The union has to be built before prepare(), not after.

    Built after, an `anyOf` goes to a profile that rejects one and the
    degradation measure reports that nothing was lost, because the transform
    never saw it. A whole run then claims a fidelity it does not have.
    """

    def sent(self, profile):
        client = RecordingClient()
        agent = ExtractionAgent(client, arm("A4", ("Length", "Mass")), profile_for(profile))
        result = agent.run(ExtractionRequest(document="d", schema=SCHEMA, branches=BRANCHES))
        return client.response_format, result.degradation

    def test_a_profile_that_takes_anyof_keeps_it(self):
        schema, degradation = self.sent("openai")
        assert "anyOf" in schema["properties"]["entities"]["items"]
        assert degradation.dropped.get("anyOf") is None

    def test_a_profile_that_refuses_anyof_never_receives_one(self):
        schema, _ = self.sent("anthropic")
        assert "anyOf" not in schema["properties"]["entities"]["items"]

    def test_refusing_it_is_recorded_as_a_loss(self):
        """Reporting fidelity 1.000 here is the bug this test exists for."""
        _, degradation = self.sent("anthropic")
        assert degradation.dropped.get("anyOf") == 1
        assert degradation.fidelity < 1.0

    def test_every_class_survives_the_flattening(self):
        schema, _ = self.sent("anthropic")
        items = schema["properties"]["entities"]["items"]
        assert items["properties"]["type"]["enum"] == ["Length", "Mass"]

    def test_the_two_profiles_report_different_fidelity(self):
        """So the report can refuse to average them."""
        _, keeps = self.sent("openai")
        _, loses = self.sent("anthropic")
        assert keeps.fidelity != loses.fidelity


class TestTheNestedUnion:
    """A union shaped like the hierarchy instead of flattened over it.

    A flat union repeats every inherited property in every branch. On the
    schema.org pool that is 3,047 property slots against the 851 the classes
    declare, and it discards the one thing the hierarchy states.
    """

    BRANCHES = {
        "Thing": {"name": {"type": "string"}},
        "CreativeWork": {"author": {"type": "string"}},
        "Book": {"isbn": {"type": "string"}},
        "Organization": {"legalName": {"type": "string"}},
    }
    PARENTS = {
        "CreativeWork": ("Thing",),
        "Book": ("CreativeWork",),
        "Organization": ("Thing",),
    }

    def built(self):
        return nested_union(self.BRANCHES, self.PARENTS)

    def test_a_single_root_is_the_whole_schema(self):
        assert self.built()["properties"]["type"]["enum"][0] == "Thing"

    def test_a_subclass_hangs_beneath_its_parent(self):
        creative = next(b for b in self.built()["anyOf"] if b.get("properties", {}).get("type", {}).get("enum"))
        assert "Book" in creative["properties"]["type"]["enum"]

    def test_an_inherited_property_is_stated_once(self):
        """The saving, and the reason the hierarchy is worth keeping."""
        rendered = json.dumps(self.built())
        assert rendered.count('"name"') == 1

    def test_every_class_is_still_reachable(self):
        rendered = json.dumps(self.built())
        assert all(name in rendered for name in self.BRANCHES)

    def test_a_leaf_pins_its_own_class(self):
        rendered = json.dumps(self.built())
        assert '"const": "Book"' in rendered

    def test_no_allof_is_used(self):
        """Every strict provider subset rejects allOf, so nesting must not
        need one. Sibling properties and anyOf are conjoined already."""
        assert "allOf" not in json.dumps(self.built())

    def test_an_empty_union_is_refused(self):
        with pytest.raises(ValueError, match="at least one branch"):
            nested_union({}, {})

    def test_a_parent_outside_the_offered_set_makes_a_root(self):
        """Offering a subclass without its parent must not lose the subclass."""
        built = nested_union({"Book": {"isbn": {"type": "string"}}}, {"Book": ("CreativeWork",)})
        assert built["properties"]["type"]["const"] == "Book"

    def test_multiple_inheritance_keeps_the_first_parent(self):
        """A tree holds one. 48 of 906 schema.org classes name two or three,
        and that loss belongs in the record, not hidden."""
        built = nested_union(
            {"Thing": {}, "Place": {}, "LocalBusiness": {"branchCode": {"type": "string"}}},
            {"Place": ("Thing",), "LocalBusiness": ("Organization", "Place")},
        )
        assert "LocalBusiness" in json.dumps(built)

    def test_a_provider_that_takes_anyof_keeps_the_nesting(self):
        prepared, degradation = prepare(self.built(), profile_for("openai"))
        assert "anyOf" in json.dumps(prepared)
        assert degradation.dropped.get("anyOf") is None

    def test_a_provider_that_refuses_it_still_reaches_every_class(self):
        prepared, _ = prepare(self.built(), profile_for("anthropic"))
        rendered = json.dumps(prepared)
        assert "anyOf" not in rendered
        assert all(name in rendered for name in ("Book", "Organization"))
