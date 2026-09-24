"""A schema this library emits must satisfy the spec it implements.

`oold-python` is the OO-LD reference implementation, and rc.3's own
`docs/migration/from-python.md` points users at `model_json_schema()` as the way
to emit a schema from a model. So what a model emits is not an internal detail:
it is the published artifact, and it has to validate.
"""

import json

import pytest
from pydantic import ConfigDict

from oold.model import LINK_NOTATIONS_ACTIVE, Link, LinkedBaseModel, LinkList, OoldField
from oold.validation import failure_reasons, validate_schema

pytestmark = pytest.mark.skipif(
    not LINK_NOTATIONS_ACTIVE,
    reason=(
        "OOLD_DESCRIPTOR_BINDING=0 selects the legacy binding, which has no "
        "schema-emission hook. It is the deprecated opt-out and is not held to "
        "the emission contract; the descriptor binding is what publishes."
    ),
)


class Org(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                "schema": "https://schema.org/",
                "id": "@id",
                "type": "@type",
                "name": "schema:name",
            },
            "$id": "https://example.org/Organization",
        }
    )
    id: str
    name: str | None = None

    @classmethod
    def get_cls_iri(cls):
        return "https://example.org/Organization"


class Person(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                "schema": "https://schema.org/",
                "id": "@id",
                "type": "@type",
                "name": "schema:name",
                # every link needs a term too, and "@type": "@id" is what makes
                # the value a reference: an unmapped property is dropped by
                # JSON-LD expansion and the round-trip check catches it
                "employer": {"@id": "schema:worksFor", "@type": "@id"},
                "mentor": {"@id": "schema:knows", "@type": "@id"},
                # a strictly array-typed property must declare @container, or a
                # single-element array compacts back to a bare value and the
                # reconstruction no longer satisfies the schema (OOLD-RT-08f2)
                "friends": {"@id": "schema:follows", "@type": "@id", "@container": "@set"},
            },
            "$id": "https://example.org/Person",
        }
    )
    id: str
    name: str | None = None
    employer: Link["Org"] = OoldField(required=True)
    mentor: Link["Person | None"] = OoldField()
    friends: LinkList["Person"] = OoldField()

    @classmethod
    def get_cls_iri(cls):
        return "https://example.org/Person"


Person.model_rebuild()


def _emit(tmp_path, schema: dict):
    schema.setdefault("$schema", "https://oo-ld.org/latest/meta/oold-meta-schema.json")
    path = tmp_path / "Person.json"
    path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    return path


def test_requiredness_is_stated_only_by_the_required_array():
    """``x-oold-required-iri`` is an oold-python annotation on a *field*, not a
    spec keyword. It carries the requirement across the point where the property
    has to leave ``required`` so the generated field is Optional (see
    ``generator.preprocess``); it must not reach the published document."""
    props = Person.export_schema()["properties"]
    assert "employer" in Person.export_schema()["required"]
    assert "x-oold-required-iri" not in props["employer"]
    assert "x-oold-link" not in props["employer"]
    # a required property may not also declare a default - nothing satisfies both
    assert "default" not in props["employer"]
    # the internal annotation still drives construction
    assert Person.__link_fields__["employer"].required_iri is True


def test_optional_links_keep_their_derived_range():
    schema = Person.export_schema()
    assert "mentor" not in schema.get("required", [])
    assert schema["properties"]["mentor"]["x-oold-range"] == "https://example.org/Person"
    assert schema["properties"]["friends"]["x-oold-range"] == "https://example.org/Person"


def test_export_schema_validates(tmp_path):
    report = validate_schema(_emit(tmp_path, Person.export_schema()))
    assert report.passed, failure_reasons(report)


def test_model_json_schema_validates(tmp_path):
    report = validate_schema(_emit(tmp_path, Person.model_json_schema()))
    assert report.passed, failure_reasons(report)


def test_a_link_declares_an_iri_family_format():
    """OOLD-EXT-6ea3 (SHOULD) wants an IRI-valued property to constrain its
    lexical form; OOLD-EXT-1f92 recommends iri-reference, which admits absolute
    IRIs, compact IRIs and context-relative references alike. It is also the
    second reference signal a frame derivation looks for (OOLD-EXT-68fa)."""
    props = Person.export_schema()["properties"]
    assert props["employer"]["format"] == "iri-reference"
    assert props["friends"]["items"]["format"] == "iri-reference"
    assert "format" not in props["friends"]  # the array itself is not an IRI


def test_a_declared_format_is_not_overwritten():
    """OSW declares `format: autocomplete` on link properties for its UI."""
    from pydantic import Field

    class M(LinkedBaseModel):
        model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/M"})
        id: str | None = None
        ref: Org | None = Field(None, json_schema_extra={"range": "Org", "format": "autocomplete"})

    M.model_rebuild()
    assert M.export_schema()["properties"]["ref"]["format"] == "autocomplete"


def test_the_frame_derivation_still_sees_our_links_as_references():
    """The schema side and the framing side must agree: both say a link is an
    IRI. reference_properties is the canonical predicate (OOLD-EXT-68fa)."""
    from oold.validation.frame import reference_properties

    assert reference_properties(Person.export_schema()) == ["employer", "mentor", "friends"]
