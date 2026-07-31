"""Meta-schema validation, pattern lint and cyclic-context detection."""

from __future__ import annotations

from oold.validation.context_graph import (
    context_file_refs,
    cyclic_scoped_contexts,
)
from oold.validation.pattern_lint import (
    array_properties_missing_container,
    context_terms,
    iri_references_missing_format,
    is_strict_array,
    lint,
)
from oold.validation.schema_checks import check_usable_as_validator, validate_against_meta

from .conftest import read

# ------------------------------------------------------------------ meta-schema validation


def test_every_committed_example_is_a_valid_oold_schema(bundle, data_dir):
    for path in sorted(data_dir.glob("*.schema.json")):
        result = validate_against_meta(read(path), bundle)
        assert result.valid, f"{path.name}: {result.errors[:2]}"


def test_jsonld_keywords_are_tolerated_as_annotations(bundle):
    """Load-bearing for the whole package, so it is asserted rather than assumed.

    JSON Schema 2020-12 tolerates unknown keywords as annotations. If it did not, `@context`
    at a schema root would make every OO-LD document invalid.
    """
    result = validate_against_meta({"@context": {"ex": "https://example.org/"}, "@id": "x", "type": "object"}, bundle)
    assert result.valid
    assert "@context" in result.jsonld_keywords_found


def test_a_malformed_keyword_is_rejected(bundle):
    result = validate_against_meta({"x-oold-instance-rdf-type": "not-an-array"}, bundle)
    assert not result.valid


def test_broken_fixture_fails_the_meta_schema(bundle, broken_dir):
    result = validate_against_meta(read(broken_dir / "invalid_meta.schema.json"), bundle)
    assert not result.valid, "x-oold-uuid: 'not-a-uuid' must fail; format has to be asserted"


def test_non_object_root_is_reported_not_raised(bundle):
    assert not validate_against_meta(["not", "an", "object"], bundle).valid


def test_uncompilable_schema_is_caught():
    assert check_usable_as_validator({"type": "string", "pattern": "([unclosed"})
    assert check_usable_as_validator({"type": "string"}) == []


# ------------------------------------------------------------------ pattern lint


def test_committed_examples_pass_the_lint(bundle, data_dir):
    for path in sorted(data_dir.glob("*.schema.json")):
        result = lint(read(path), bundle)
        assert not result.failed, f"{path.name}: {result.to_dict()}"


def test_xsd_string_coercion_is_a_must_failure(bundle, broken_dir):
    result = lint(read(broken_dir / "xsd_string_coercion.schema.json"), bundle)
    assert result.schema_errors, "a term coercing to xsd:string never round-trips"
    assert result.failed


def test_array_without_container_is_a_must_failure(bundle, broken_dir):
    result = lint(read(broken_dir / "array_without_container.schema.json"), bundle)
    assert result.missing_container == ["tags"]
    assert result.failed


def test_context_terms_skips_keywords_and_string_definitions():
    terms = context_terms({"@version": 1.1, "plain": "ex:plain", "full": {"@id": "ex:full"}})
    assert terms == {"full": {"@id": "ex:full"}}


def test_is_strict_array():
    assert is_strict_array({"type": "array"})
    assert is_strict_array({"items": {"type": "string"}})
    assert not is_strict_array({"type": ["array", "string"]})
    assert not is_strict_array({"type": "string"})


def test_container_forms_are_all_accepted():
    for container in ("@set", "@list", ["@set"], ["@list", "@index"]):
        schema = {
            "@context": [{"t": {"@id": "ex:t", "@container": container}}],
            "properties": {"t": {"type": "array"}},
        }
        assert array_properties_missing_container(schema) == []


def test_container_check_ignores_unmapped_and_flexible_properties():
    # No local term at all: mapped by an inherited context, so out of scope here.
    assert (
        array_properties_missing_container({
            "@context": [{"other": "ex:other"}],
            "properties": {"tags": {"type": "array"}},
        })
        == []
    )
    # Cardinality-flexible: the scalar form still validates after a round-trip.
    assert (
        array_properties_missing_container({
            "@context": [{"tags": {"@id": "ex:t"}}],
            "properties": {"tags": {"type": ["array", "string"]}},
        })
        == []
    )


def test_iri_format_recommendation():
    base = {"@context": [{"knows": {"@id": "ex:knows", "@type": "@id"}}]}
    assert iri_references_missing_format({
        **base,
        "properties": {"knows": {"type": "string", "x-oold-range": "P"}},
    }) == ["knows"]
    assert (
        iri_references_missing_format({
            **base,
            "properties": {"knows": {"type": "string", "format": "iri-reference", "x-oold-range": "P"}},
        })
        == []
    )
    assert iri_references_missing_format({
        **base,
        "properties": {"knows": {"type": "array", "items": {"type": "string", "x-oold-range": "P"}}},
    }) == ["knows[]"]
    # Without x-oold-range it is not a typed reference, so the recommendation does not apply.
    assert iri_references_missing_format({**base, "properties": {"knows": {"type": "string"}}}) == []


def test_iri_format_finding_is_a_warning_not_a_failure(bundle):
    result = lint(
        {
            "@context": [{"knows": {"@id": "ex:knows", "@type": "@id"}}],
            "properties": {"knows": {"type": "string", "x-oold-range": "P"}},
        },
        bundle,
    )
    assert result.has_warning
    assert not result.failed, "the IRI lexical form is a SHOULD, so it must not fail a run"


# ------------------------------------------------------------------ context graph


def test_context_file_refs_finds_parent_and_scoped_references():
    context = [
        "Parent.schema.json",
        {"ex": "https://example.org/", "p": {"@id": "ex:p", "@context": "Scoped.schema.json"}},
    ]
    assert context_file_refs(context) == {"Parent.schema.json", "Scoped.schema.json"}


def test_context_file_refs_ignores_ordinary_iris():
    assert context_file_refs({"ex": "https://example.org/", "p": "ex:p"}) == set()


def test_committed_examples_have_no_cyclic_scoped_contexts(data_dir):
    schemas = {p.name: read(p) for p in data_dir.glob("*.schema.json")}
    assert cyclic_scoped_contexts(schemas) == set()


def test_a_cycle_is_detected_and_propagates_to_referrers():
    schemas = {
        "A.schema.json": {"@context": [{"b": {"@id": "ex:b", "@context": "B.schema.json"}}]},
        "B.schema.json": {"@context": [{"a": {"@id": "ex:a", "@context": "A.schema.json"}}]},
        "C.schema.json": {"@context": ["A.schema.json"]},
        "D.schema.json": {"@context": [{"x": "ex:x"}]},
    }
    found = cyclic_scoped_contexts(schemas)
    assert found == {"A.schema.json", "B.schema.json", "C.schema.json"}
    assert "D.schema.json" not in found


def test_unreadable_document_contributes_no_edges():
    assert cyclic_scoped_contexts({"A.schema.json": "not a dict"}) == set()


def test_reference_outside_the_set_is_ignored():
    assert cyclic_scoped_contexts({"A.schema.json": {"@context": ["Elsewhere.schema.json"]}}) == set()
