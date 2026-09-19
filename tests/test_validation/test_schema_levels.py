"""A subclass emits its own schema level, composed onto its bases with allOf.

The schema hierarchy mirrors the class hierarchy: `Person.json` carries what
`Person` adds and refers to `Entity.json` for the rest. Three rc.3 rules turn
this from a style preference into a requirement - every `$ref` is reflected in
`@context` (OOLD-CMP-b926), multiple `$ref`s list their contexts in allOf order
(OOLD-CMP-e4a3), and composition is narrow-only (OOLD-CMP-f3c7), which a
derived schema restating an inherited property can silently break.
"""

import json

import pytest
from pydantic import ConfigDict

from oold.model import LINK_NOTATIONS_ACTIVE, Link, LinkedBaseModel, OoldField
from oold.static import SchemaExportMode
from oold.validation import failure_reasons, validate_schema

pytestmark = pytest.mark.skipif(
    not LINK_NOTATIONS_ACTIVE,
    reason="the legacy binding is the deprecated opt-out and does not publish",
)

# relative, as the committed fixtures are (tests/data/oold/Contact.schema.json):
# $id, the allOf $ref and the @context entry are the same reference, so a
# schema published beside its base resolves without a network fetch
ENTITY = "Entity.schema.json"
PERSON = "Person.schema.json"


class Entity(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                "schema": "https://schema.org/",
                "id": "@id",
                "type": "@type",
                "name": "schema:name",
            },
            "$id": ENTITY,
        }
    )
    # optional, as the committed Thing.schema.json fixture has it: an instance
    # whose only content is its @id compacts back to a bare IRI, so a base whose
    # sole required property is the identifier cannot round-trip
    id: str | None = None
    name: str | None = None

    @classmethod
    def get_cls_iri(cls):
        return ENTITY


class Person(Entity):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": [
                ENTITY,
                {"father": {"@id": "schema:parent", "@type": "@id"}},
            ],
            "$id": PERSON,
        }
    )
    father: Link["Person | None"] = OoldField()

    @classmethod
    def get_cls_iri(cls):
        return PERSON


Person.model_rebuild()


def _partial(model_cls) -> dict:
    return model_cls.export_schema(mode=SchemaExportMode.PARTIAL)


def test_a_subclass_emits_only_its_own_properties():
    """`model_fields` is flattened by pydantic - it holds inherited fields too -
    so building the level from it produced a monolithic schema. Restating an
    inherited property also risks relaxing it, which OOLD-CMP-f3c7 forbids."""
    schema = _partial(Person)
    assert sorted(schema["properties"]) == ["father"]
    assert "id" not in schema.get("required", [])


def test_the_level_composes_onto_its_base_with_allof():
    schema = _partial(Person)
    assert schema["allOf"] == [{"$ref": ENTITY}]


def test_the_context_mirrors_allof_in_the_same_order():
    """OOLD-CMP-b926 and OOLD-CMP-e4a3: a schema must be usable as a JSON-LD
    context with no further processing, so every $ref is reflected in @context,
    and multiple refs appear in allOf order."""
    schema = _partial(Person)
    refs = [entry["$ref"] for entry in schema["allOf"]]
    context = schema["@context"]
    assert isinstance(context, list)
    assert [c for c in context if isinstance(c, str)] == refs


def test_a_root_class_is_unchanged():
    """Nothing to compose onto, so no allOf and every property is its own."""
    schema = _partial(Entity)
    assert "allOf" not in schema
    assert sorted(schema["properties"]) == ["id", "name"]


def test_full_mode_still_flattens():
    """FULL stays the default and keeps its meaning: one self-contained schema."""
    schema = Entity.export_schema()
    assert sorted(schema["properties"]) == ["id", "name"]
    assert sorted(Person.export_schema()["properties"]) == ["father", "id", "name"]


def test_both_levels_validate(tmp_path):
    """Written side by side, so the @context reference resolves locally -
    validate_schema reads sibling schemas for exactly this reason."""
    for name, schema in (("Entity.schema", Entity.export_schema()), ("Person.schema", _partial(Person))):
        schema.setdefault("$schema", "https://oo-ld.org/latest/meta/oold-meta-schema.json")
        (tmp_path / f"{name}.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")
    report = validate_schema(tmp_path / "Person.schema.json")
    assert report.passed, failure_reasons(report)


def test_a_definition_reached_only_through_another_is_kept():
    """Reachability is transitive: `$defs.Outer` is referenced from the body and
    itself references `$defs.Inner`, so neither is dead. Pruning only what the
    body points at directly would delete Inner and break the schema."""
    from oold.static import _prune_unreferenced_defs

    schema = {
        "properties": {"a": {"$ref": "#/$defs/Outer"}},
        "$defs": {
            "Outer": {"properties": {"b": {"$ref": "#/$defs/Inner"}}},
            "Inner": {"type": "string"},
            "Orphan": {"type": "string"},
        },
    }
    _prune_unreferenced_defs(schema)
    assert sorted(schema["$defs"]) == ["Inner", "Outer"]


def test_defs_disappears_when_nothing_survives():
    from oold.static import _prune_unreferenced_defs

    schema = {"properties": {}, "$defs": {"Orphan": {"type": "string"}}}
    _prune_unreferenced_defs(schema)
    assert "$defs" not in schema


def test_the_v1_underscore_spelling_is_normalised_too():
    """pydantic v1 cannot pass a hyphenated keyword to Field(), so downstream
    spells it with underscores. Both reach `required` and neither survives."""
    from oold.static import _state_requiredness_in_the_required_array

    schema = {
        "properties": {
            "a": {"type": "string", "x_oold_required_iri": True, "default": None},
            "b": {"type": "string", "x-oold-required-iri": True},
            "c": {"type": "string", "default": None},
        }
    }
    _state_requiredness_in_the_required_array(schema)
    assert sorted(schema["required"]) == ["a", "b"]
    assert "default" not in schema["properties"]["a"]
    assert not any(k.startswith(("x-oold-required", "x_oold_required")) for k in schema["properties"]["a"])
    # an optional property keeps its default and stays out of `required`
    assert schema["properties"]["c"]["default"] is None
