"""The narrow checks that each enforce one normative rule.

Every check gets both a violating and a conforming case. A check that only ever fires is as
useless as one that never does, and these run over real OO-LD schemas where a false positive
would be expensive.
"""

from __future__ import annotations

import pytest

from oold.validation.check_registry import CHECKS, ContextView, run_rule_checks, severity
from oold.validation.meta_store import latest_version, load_tracked

#: The catalogue actually shipped for the newest tracked version. Severity is read from it rather
#: than hardcoded here, so if upstream relaxes a MUST to a SHOULD these tests report the change
#: instead of silently disagreeing with the specification.
CATALOG = {r["id"]: r for r in load_tracked(latest_version()).rules}

#: The ten self-contained rule checks, in the order they are declared - the same slice
#: `run_rule_checks` executes.
SELF_CONTAINED_CHECKS = tuple(c for c in CHECKS if c.run)


def _findings(schema: dict, context: ContextView | None = None):
    return {f.check_id: f for f in run_rule_checks(schema, context or ContextView(), CATALOG)}


def outcome(check_id: str, schema: dict, context: ContextView | None = None) -> str:
    return _findings(schema, context)[check_id].status


def message(check_id: str, schema: dict, context: ContextView | None = None) -> str:
    return _findings(schema, context)[check_id].message


# ------------------------------------------------------------------ registry


def test_every_check_names_a_rule_that_exists():
    for check in SELF_CONTAINED_CHECKS:
        assert check.rule.startswith("OOLD-"), check.id
        assert check.id.startswith("rule."), check.id
        assert check.rule in CATALOG, f"{check.id} cites {check.rule}, absent from the catalogue"


def test_severity_is_read_from_the_specification_not_hardcoded():
    """A MUST fails and a SHOULD warns because the catalogue says so.

    Nothing in this package repeats the level, so upstream relaxing a MUST changes the outcome
    with no code change here.
    """
    assert severity(CATALOG["OOLD-VER-001"]) == "fail", "OOLD-VER-001 is a MUST"
    assert severity(CATALOG["OOLD-VER-002"]) == "warn", "OOLD-VER-002 is a SHOULD"
    assert severity(CATALOG["OOLD-RT-001"]) == "fail", "MUST NOT is also a failure"


def test_a_rule_absent_from_the_catalogue_is_skipped():
    """A version that never stated a requirement must not be judged against it."""
    without = {k: v for k, v in CATALOG.items() if k != "OOLD-VER-001"}
    findings = {f.check_id: f for f in run_rule_checks({}, ContextView(), without)}
    assert findings["rule.id"].status == "skip"
    assert "not stated" in findings["rule.id"].message


def test_a_deprecated_rule_is_skipped():
    retired = dict(CATALOG)
    retired["OOLD-VER-001"] = {**retired["OOLD-VER-001"], "deprecated": True, "superseded_by": ["OOLD-VER-009"]}
    findings = {f.check_id: f for f in run_rule_checks({}, ContextView(), retired)}
    assert findings["rule.id"].status == "skip"
    assert "deprecated" in findings["rule.id"].message
    assert "OOLD-VER-009" in findings["rule.id"].message


# ------------------------------------------------------------------ OOLD-VER-001 / CMP-005


def test_missing_id_is_reported():
    assert outcome("rule.id", {"type": "object"}) == "fail"
    assert outcome("rule.id", {"$id": "Thing.schema.json"}) == "ok"


def test_id_fragment():
    assert outcome("rule.id-fragment", {"$id": "https://example.org/T.json#/$defs/X"}) == "fail"
    assert outcome("rule.id-fragment", {"$id": "https://example.org/T.json"}) == "ok"
    # An *empty* fragment is explicitly permitted by JSON Schema.
    assert outcome("rule.id-fragment", {"$id": "https://example.org/T.json#"}) == "ok"


# ------------------------------------------------------------------ OOLD-EXT-005


def test_range_must_use_x_oold_ref_not_ref():
    bad = {"properties": {"affiliation": {"x-oold-range": {"allOf": [{"$ref": "Organization.schema.json"}]}}}}
    good = {"properties": {"affiliation": {"x-oold-range": {"allOf": [{"x-oold-ref": "Organization.schema.json"}]}}}}
    assert outcome("rule.range-ref", bad) == "fail"
    assert "x-oold-ref" in message("rule.range-ref", bad)
    assert outcome("rule.range-ref", good) == "ok"


def test_a_plain_string_range_is_not_flagged():
    assert outcome("rule.range-ref", {"properties": {"a": {"x-oold-range": "schema:Person"}}}) == "ok"


def test_a_ref_outside_a_range_is_not_flagged():
    """Ordinary composition uses $ref and must stay untouched."""
    schema = {"allOf": [{"$ref": "Thing.schema.json"}], "properties": {"a": {"$ref": "X.json"}}}
    assert outcome("rule.range-ref", schema) == "ok"


# ------------------------------------------------------------------ OOLD-INS-002


def test_pinned_type_must_agree_with_the_declared_rdf_type():
    base = {"x-oold-instance-rdf-type": ["schema:Person"]}
    assert outcome("rule.instance-type", {**base, "properties": {"type": {"const": "schema:Place"}}}) == "fail"
    assert outcome("rule.instance-type", {**base, "properties": {"type": {"const": "schema:Person"}}}) == "ok"
    assert outcome("rule.instance-type", {**base, "properties": {"type": {"default": ["schema:Person"]}}}) == "ok"


def test_an_unpinned_type_cannot_disagree():
    """`type: string` says nothing about what an instance will carry."""
    schema = {"x-oold-instance-rdf-type": ["schema:Person"], "properties": {"type": {"type": "string"}}}
    assert outcome("rule.instance-type", schema) == "ok"


def test_no_declared_rdf_type_means_nothing_to_disagree_with():
    assert outcome("rule.instance-type", {"properties": {"type": {"const": "schema:Place"}}}) == "ok"


def test_inherited_rdf_type_is_used():
    """After dereferencing, a subclass carries its parent's declaration under allOf."""
    schema = {
        "allOf": [{"x-oold-instance-rdf-type": ["schema:Person"]}],
        "properties": {"type": {"const": "schema:Place"}},
    }
    assert outcome("rule.instance-type", schema) == "fail"


# ------------------------------------------------------------------ OOLD-INS-009


def test_free_text_range_must_not_be_coerced_to_iri():
    context = ContextView(terms={"address": {"@id": "schema:address", "@type": "@id"}})
    mixed = {"properties": {"address": {"anyOf": [{"type": "string"}, {"type": "object", "properties": {"id": {}}}]}}}
    assert outcome("rule.free-text-iri", mixed, context) == "fail"


def test_a_pure_reference_property_is_not_flagged():
    """A string-only property under @type @id is the ordinary bare-IRI form."""
    context = ContextView(terms={"knows": {"@id": "schema:knows", "@type": "@id"}})
    schema = {"properties": {"knows": {"type": "string", "format": "iri-reference"}}}
    assert outcome("rule.free-text-iri", schema, context) == "ok"


def test_a_mixed_range_without_id_coercion_is_fine():
    """The value-form pattern: a plain term, so the value shape disambiguates."""
    context = ContextView(terms={"address": {"@id": "schema:address"}})
    schema = {"properties": {"address": {"anyOf": [{"type": "string"}, {"type": "object"}]}}}
    assert outcome("rule.free-text-iri", schema, context) == "ok"


def test_an_iri_branch_is_not_mistaken_for_free_text():
    """A string branch carrying a format or a range is a reference, not free text."""
    context = ContextView(terms={"a": {"@id": "ex:a", "@type": "@id"}})
    schema = {"properties": {"a": {"anyOf": [{"type": "string", "format": "iri-reference"}, {"type": "object"}]}}}
    assert outcome("rule.free-text-iri", schema, context) == "ok"


# ------------------------------------------------------------------ OOLD-INS-005


def test_a_closed_object_must_permit_schema_and_context():
    closed = {"additionalProperties": False, "properties": {"name": {}}}
    assert outcome("rule.closed-object", closed) == "fail"
    permitted = {
        "additionalProperties": False,
        "properties": {"name": {}, "$schema": {}, "@context": {}},
    }
    assert outcome("rule.closed-object", permitted) == "ok"


def test_an_open_object_is_not_flagged():
    assert outcome("rule.closed-object", {"properties": {"name": {}}}) == "ok"


def test_unevaluated_properties_false_is_treated_as_closed():
    assert outcome("rule.closed-object", {"unevaluatedProperties": False, "properties": {}}) == "fail"


# ------------------------------------------------------------------ SHOULD-level


def test_version_and_alias_and_dialect_warn_rather_than_fail():
    assert outcome("rule.version", {}) == "warn"
    assert outcome("rule.version", {"x-oold-version": "1.0.0"}) == "ok"

    assert outcome("rule.id-alias", {}, ContextView(terms={"name": "ex:name"})) == "warn"
    assert outcome("rule.id-alias", {}, ContextView(terms={"id": "@id"})) == "ok"
    assert outcome("rule.id-alias", {}, ContextView(terms={"identifier": {"@id": "@id"}})) == "ok"

    assert outcome("rule.dialect", {"$schema": "https://json-schema.org/draft/2020-12/schema"}) == "warn"
    assert outcome("rule.dialect", {"$schema": "https://oo-ld.org/latest/meta/oold-meta-schema.json"}) == "ok"


def test_the_dialect_check_accepts_either_canonical_domain():
    """The $id domain has moved once and releases stamp a version, so match the file name."""
    for url in (
        "https://oo-ld.org/latest/meta/oold-meta-schema.json",
        "https://oo-ld.github.io/oold-schema/latest/meta/oold-meta-schema.json",
        "https://oo-ld.org/0.8.0/meta/oold-meta-schema.json",
    ):
        assert outcome("rule.dialect", {"$schema": url}) == "ok", url


def test_processing_mode_uses_the_resolved_context():
    """A schema inheriting @version from a parent context must not be flagged.

    This was a real false positive: reading only the schema's own `@context` warned on every
    subclass, because inheritance puts `@version` in the parent.
    """
    assert outcome("rule.processing-mode", {}, ContextView(entries=[{"@version": 1.1}])) == "ok"
    assert outcome("rule.processing-mode", {}, ContextView(entries=[{"ex": "https://x/"}])) == "warn"
    # Inherited: the resolved form is a list whose first entry came from the parent schema.
    inherited = ContextView(entries=[{"@version": 1.1, "id": "@id"}, {"ex": "https://x/"}])
    assert outcome("rule.processing-mode", {}, inherited) == "ok"


def test_processing_mode_rejects_the_string_form():
    """`"1.1"` is a string; JSON-LD requires the number."""
    assert outcome("rule.processing-mode", {}, ContextView(entries=[{"@version": "1.1"}])) == "warn"


# ------------------------------------------------------------------ against the real corpus


def test_no_must_level_rule_fires_on_the_upstream_examples(data_dir):
    """The reference examples are conforming, so any MUST-level hit is a false positive."""
    from oold.validation import Options, validate_directory

    report = validate_directory(data_dir, Options(meta=("latest",), offline=True))
    hits = [c for c in report.checks if c.id.startswith("rule.") and c.status == "fail"]
    assert not hits, [f"{c.id} {c.target}: {c.message}" for c in hits]


@pytest.mark.parametrize("check", SELF_CONTAINED_CHECKS, ids=lambda c: c.id)
def test_every_check_runs_on_every_example(check, data_dir):
    """No check may crash on a real schema; each must produce a verdict."""
    from oold.validation import Options, validate_directory

    report = validate_directory(data_dir, Options(meta=("latest",), offline=True))
    produced = [c for c in report.checks if c.id == check.id]
    assert produced, f"{check.id} produced no finding at all"
