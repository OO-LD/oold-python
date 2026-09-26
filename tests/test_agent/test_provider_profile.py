"""Per-provider schema preparation.

Each assertion pins a documented provider limit. If a provider widens its
subset, the test that says so should be the thing that fails.
"""

import pytest

from oold.agent import prepare, profile_for, schema_hash

RECURSIVE = {
    "type": "object",
    "$defs": {
        "Node": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "children": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/Node"},
                },
            },
            "required": ["label"],
        }
    },
    "properties": {"root": {"$ref": "#/$defs/Node"}},
    "required": ["root"],
}

CONSTRAINED = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "maxLength": 200},
        "count": {"type": "integer", "minimum": 0, "maximum": 10},
    },
    "required": ["name"],
}

INHERITED = {
    "@context": ["Thing.schema.json", {}],
    "x-oold-iri": "https://schema.org/Person",
    "allOf": [{"$ref": "#/$defs/Thing"}],
    "$defs": {
        "Thing": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
    },
    "type": "object",
    "properties": {"email": {"type": "string", "format": "email"}},
}


def keywords(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        found.update(node)
        for value in node.values():
            keywords(value, found)
    elif isinstance(node, list):
        for value in node:
            keywords(value, found)
    return found


class TestCombinators:
    @pytest.mark.parametrize("provider", ["openai", "anthropic", "google"])
    def test_all_of_never_survives(self, provider):
        """allOf is rejected in strict mode by all three."""
        prepared, report = prepare(INHERITED, profile_for(provider))
        assert "allOf" not in keywords(prepared)
        assert report.dropped.get("allOf") == 1

    def test_all_of_merges_the_parent_in(self):
        prepared, _ = prepare(INHERITED, profile_for("openai"))
        assert set(prepared["properties"]) == {"name", "email"}

    def test_native_keeps_the_schema_intact(self):
        prepared, report = prepare(INHERITED, profile_for("native"))
        assert "allOf" in keywords(prepared)
        assert report.dropped == {}
        assert report.semantics_dropped == 0


class TestRecursion:
    def test_openai_keeps_a_recursive_ref(self):
        prepared, report = prepare(RECURSIVE, profile_for("openai"))
        assert "$ref" in keywords(prepared)
        assert report.recursion_cut == 0

    def test_anthropic_cuts_the_cycle(self):
        """Anthropic does not support recursive $ref, so it has to end."""
        prepared, report = prepare(RECURSIVE, profile_for("anthropic"))
        assert "$ref" not in keywords(prepared)
        assert report.recursion_cut >= 1

    def test_a_cut_schema_is_still_a_schema(self):
        prepared, _ = prepare(RECURSIVE, profile_for("anthropic"))
        assert prepared["type"] == "object"
        assert "root" in prepared["properties"]


class TestConstraints:
    def test_anthropic_moves_constraints_into_the_description(self):
        """Anthropic rejects minimum and maxLength; the SDKs describe them."""
        prepared, report = prepare(CONSTRAINED, profile_for("anthropic"))
        assert "maxLength" not in keywords(prepared)
        assert "minimum" not in keywords(prepared)
        assert "maxLength: 200" in prepared["properties"]["name"]["description"]
        assert report.constraints_described == 3

    def test_openai_keeps_constraints(self):
        prepared, report = prepare(CONSTRAINED, profile_for("openai"))
        assert "maxLength" in keywords(prepared)
        assert report.constraints_described == 0


class TestRequiredAndAdditional:
    def test_openai_requires_every_property(self):
        prepared, report = prepare(CONSTRAINED, profile_for("openai"))
        assert set(prepared["required"]) == {"name", "count"}
        assert report.made_required == 1

    def test_a_property_made_required_becomes_nullable(self):
        prepared, _ = prepare(CONSTRAINED, profile_for("openai"))
        assert "null" in prepared["properties"]["count"]["type"]

    def test_google_leaves_optional_properties_optional(self):
        prepared, report = prepare(CONSTRAINED, profile_for("google"))
        assert prepared["required"] == ["name"]
        assert report.made_required == 0

    @pytest.mark.parametrize("provider", ["openai", "anthropic"])
    def test_additional_properties_is_closed(self, provider):
        prepared, _ = prepare(CONSTRAINED, profile_for(provider))
        assert prepared["additionalProperties"] is False

    def test_google_does_not_require_a_closed_object(self):
        prepared, _ = prepare(CONSTRAINED, profile_for("google"))
        assert "additionalProperties" not in prepared

    def test_anthropic_caps_optional_properties_at_24(self):
        wide = {
            "type": "object",
            "properties": {f"p{i}": {"type": "string"} for i in range(40)},
            "required": [],
        }
        prepared, report = prepare(wide, profile_for("anthropic"))
        assert len(prepared["properties"]) == 24
        assert report.dropped["optional-property-overflow"] == 16


class TestGrounding:
    def test_grounding_keeps_the_context_and_the_iris(self):
        prepared, report = prepare(
            INHERITED, profile_for("openai"), grounding=True
        )
        assert "@context" in prepared
        assert prepared["x-oold-iri"] == "https://schema.org/Person"
        assert report.semantics_dropped == 0

    def test_flattening_removes_them_and_counts_it(self):
        prepared, report = prepare(
            INHERITED, profile_for("openai"), grounding=False
        )
        assert "@context" not in prepared
        assert "x-oold-iri" not in prepared
        assert report.semantics_dropped == 2

    def test_grounding_is_the_only_difference_between_the_two(self):
        grounded, _ = prepare(INHERITED, profile_for("openai"), grounding=True)
        flat, _ = prepare(INHERITED, profile_for("openai"), grounding=False)
        for keyword in ("@context", "x-oold-iri"):
            grounded.pop(keyword, None)
        assert grounded == flat


class TestDegradation:
    def test_native_loses_nothing(self):
        _, report = prepare(INHERITED, profile_for("native"))
        assert report.fidelity == pytest.approx(1.0)

    def test_anthropic_loses_more_than_openai(self):
        _, strict = prepare(CONSTRAINED, profile_for("anthropic"))
        _, lenient = prepare(CONSTRAINED, profile_for("openai"))
        assert len(strict.dropped) > len(lenient.dropped)

    def test_the_report_is_serialisable(self):
        _, report = prepare(INHERITED, profile_for("anthropic"))
        described = report.describe()
        assert set(described) >= {"fidelity", "dropped", "semantics_dropped"}

    def test_fidelity_is_one_when_nothing_was_there_to_lose(self):
        _, report = prepare({}, profile_for("anthropic"))
        assert report.fidelity == 1.0


class TestReproducibility:
    def test_preparation_is_deterministic(self):
        first, _ = prepare(INHERITED, profile_for("anthropic"))
        second, _ = prepare(INHERITED, profile_for("anthropic"))
        assert schema_hash(first) == schema_hash(second)

    def test_different_providers_give_different_hashes(self):
        a, _ = prepare(CONSTRAINED, profile_for("anthropic"))
        b, _ = prepare(CONSTRAINED, profile_for("openai"))
        assert schema_hash(a) != schema_hash(b)

    def test_the_input_is_not_mutated(self):
        before = dict(CONSTRAINED)
        prepare(CONSTRAINED, profile_for("openai"))
        assert CONSTRAINED == before

    def test_an_unknown_profile_is_refused_rather_than_guessed(self):
        """A model name must never select a profile by substring."""
        with pytest.raises(KeyError, match="unknown provider profile"):
            profile_for("gpt-oss-120b")
