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
    assert severity(CATALOG["OOLD-VER-3b96"]) == "fail", "OOLD-VER-3b96 is a MUST"
    assert severity(CATALOG["OOLD-VER-3662"]) == "warn", "OOLD-VER-3662 is a SHOULD"
    assert severity(CATALOG["OOLD-RT-d9bd"]) == "fail", "MUST NOT is also a failure"


def test_a_rule_absent_from_the_catalogue_is_skipped():
    """A version that never stated a requirement must not be judged against it."""
    without = {k: v for k, v in CATALOG.items() if k != "OOLD-VER-3b96"}
    findings = {f.check_id: f for f in run_rule_checks({}, ContextView(), without)}
    assert findings["rule.id"].status == "skip"
    assert "not stated" in findings["rule.id"].message


def test_a_deprecated_rule_is_skipped():
    retired = dict(CATALOG)
    retired["OOLD-VER-3b96"] = {**retired["OOLD-VER-3b96"], "deprecated": True, "superseded_by": ["OOLD-VER-0009"]}
    findings = {f.check_id: f for f in run_rule_checks({}, ContextView(), retired)}
    assert findings["rule.id"].status == "skip"
    assert "deprecated" in findings["rule.id"].message
    assert "OOLD-VER-0009" in findings["rule.id"].message


# ------------------------------------------------------------------ OOLD-VER-3b96 / CMP-dd2b


def test_missing_id_is_reported():
    assert outcome("rule.id", {"type": "object"}) == "fail"
    assert outcome("rule.id", {"$id": "Thing.schema.json"}) == "ok"


def test_id_fragment():
    assert outcome("rule.id-fragment", {"$id": "https://example.org/T.json#/$defs/X"}) == "fail"
    assert outcome("rule.id-fragment", {"$id": "https://example.org/T.json"}) == "ok"
    # An *empty* fragment is explicitly permitted by JSON Schema.
    assert outcome("rule.id-fragment", {"$id": "https://example.org/T.json#"}) == "ok"


# ------------------------------------------------------------------ OOLD-EXT-3fe9


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


# ------------------------------------------------------------------ OOLD-INS-4b5c


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


# ------------------------------------------------------------------ OOLD-INS-2e5d


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


# ------------------------------------------------------------------ OOLD-INS-ba9e


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


# ------------------------------------------------------------------ OOLD-VER-edb9


def test_uuid_annotation_must_be_present_and_valid():
    assert outcome("rule.uuid", {}) == "warn"
    assert outcome("rule.uuid", {"x-oold-uuid": "not-a-uuid"}) == "warn"
    assert outcome("rule.uuid", {"x-oold-uuid": "b5203131-7321-46bb-8a11-acb3d1015840"}) == "ok"


def test_uuid_annotation_accepts_the_urn_prefix():
    """`urn:uuid:...` is a legitimate way to write a UUID value."""
    assert outcome("rule.uuid", {"x-oold-uuid": "urn:uuid:b5203131-7321-46bb-8a11-acb3d1015840"}) == "ok"


# ------------------------------------------------------------------ OOLD-EXT-dd76


def test_multilang_keyword_needs_its_plain_default():
    assert outcome("rule.multilang-default", {"x-oold-multilang-title": {"en": "Person"}}) == "warn"
    assert outcome("rule.multilang-default", {"x-oold-multilang-description": {"en": "..."}}) == "warn"
    conforming = {"x-oold-multilang-title": {"en": "Person"}, "title": "Person"}
    assert outcome("rule.multilang-default", conforming) == "ok"


def test_a_schema_using_neither_multilang_keyword_is_not_judged():
    """The word "still" in the rule scopes it to schemas that use the multilingual keywords."""
    assert outcome("rule.multilang-default", {}) == "ok"


# ------------------------------------------------------------------ OOLD-CMP-53bf


def test_base_alignment_flags_a_mismatched_base():
    schema = {"$id": "https://example.org/schemas/A.schema.json"}
    context = ContextView(entries=[{"@base": "https://example.org/other/"}])
    assert outcome("rule.base-alignment", schema, context) == "warn"
    assert "@base" in message("rule.base-alignment", schema, context)


def test_base_alignment_accepts_an_aligned_base():
    schema = {"$id": "https://example.org/schemas/A.schema.json"}
    context = ContextView(entries=[{"@base": "https://example.org/schemas/"}])
    assert outcome("rule.base-alignment", schema, context) == "ok"


def test_base_alignment_is_not_judged_without_both_an_id_and_a_base():
    assert outcome("rule.base-alignment", {}) == "ok"
    assert outcome("rule.base-alignment", {"$id": "A.schema.json"}) == "ok"


# ------------------------------------------------------------------ OOLD-CMP-5266


def test_scoped_context_flags_a_ref_embed_with_no_scoped_context():
    schema = {"properties": {"address": {"type": "object", "$ref": "Address.schema.json"}}}
    context = ContextView(terms={"address": {"@id": "schema:address"}})
    assert outcome("rule.scoped-context", schema, context) == "warn"
    assert "Address.schema.json" in message("rule.scoped-context", schema, context)


def test_scoped_context_accepts_a_ref_embed_with_a_scoped_context():
    schema = {"properties": {"address": {"type": "object", "$ref": "Address.schema.json"}}}
    context = ContextView(terms={"address": {"@id": "schema:address", "@context": "Address.schema.json"}})
    assert outcome("rule.scoped-context", schema, context) == "ok"


def test_an_inline_embed_is_not_flagged():
    """The exception is for a cyclic embed graph, which only a $ref-based embed can form."""
    schema = {"properties": {"address": {"type": "object", "properties": {"street": {"type": "string"}}}}}
    context = ContextView(terms={"address": {"@id": "schema:address"}})
    assert outcome("rule.scoped-context", schema, context) == "ok"


def test_a_self_reference_is_not_flagged():
    """A schema cannot scope a remote context onto itself without recursing."""
    schema = {"$id": "Person.schema.json", "properties": {"friend": {"$ref": "Person.schema.json"}}}
    context = ContextView(terms={"friend": {"@id": "schema:knows"}})
    assert outcome("rule.scoped-context", schema, context) == "ok"


def test_a_property_with_no_term_at_all_is_not_flagged():
    """A different check covers a property with no @context term."""
    schema = {"properties": {"address": {"$ref": "Address.schema.json"}}}
    assert outcome("rule.scoped-context", schema, ContextView()) == "ok"


def test_a_scalar_range_reference_is_not_flagged():
    """x-oold-range/x-oold-ref is a scalar reference, not an embedded object."""
    schema = {"properties": {"worksFor": {"x-oold-range": {"allOf": [{"x-oold-ref": "Organization.schema.json"}]}}}}
    context = ContextView(terms={"worksFor": {"@id": "schema:worksFor"}})
    assert outcome("rule.scoped-context", schema, context) == "ok"


# ------------------------------------------------------------------ OOLD-EXT-ef09


def test_multilang_shape_must_be_bcp47_keys_with_string_values():
    assert outcome("rule.multilang-shape", {"x-oold-multilang-title": {"en": "Person", "de": "Person"}}) == "ok"
    assert outcome("rule.multilang-shape", {"x-oold-multilang-title": "Person"}) == "fail"
    assert outcome("rule.multilang-shape", {"x-oold-multilang-description": {"???": "text"}}) == "fail"
    assert outcome("rule.multilang-shape", {"x-oold-multilang-title": {"en": 1}}) == "fail"


def test_multilang_shape_accepts_a_regional_subtag():
    """`en-GB` is a legal, non-two-letter-only BCP 47 tag."""
    assert outcome("rule.multilang-shape", {"x-oold-multilang-title": {"en-GB": "Colour"}}) == "ok"


def test_a_schema_using_neither_multilang_keyword_is_not_judged_by_shape():
    assert outcome("rule.multilang-shape", {}) == "ok"


# ------------------------------------------------------------------ OOLD-EXT-af50


def test_dialect_version_requires_2020_12_or_the_oold_dialect():
    assert outcome("rule.dialect-version", {"$schema": "http://json-schema.org/draft-07/schema#"}) == "fail"
    assert outcome("rule.dialect-version", {"$schema": "https://json-schema.org/draft/2020-12/schema"}) == "ok"
    assert outcome("rule.dialect-version", {"$schema": "https://oo-ld.org/latest/meta/oold-meta-schema.json"}) == "ok"


def test_dialect_version_is_not_judged_when_schema_is_absent():
    """`rule.dialect` already reports the absence; judging it here too would double-report."""
    assert outcome("rule.dialect-version", {}) == "ok"


# ------------------------------------------------------------------ OOLD-CMP-e4a3


def test_context_array_order_must_match_allof():
    schema = {
        "allOf": [{"$ref": "Thing.schema.json"}, {"$ref": "Person.schema.json"}],
        "@context": ["Thing.schema.json", "Person.schema.json"],
    }
    assert outcome("rule.context-array-order", schema) == "ok"


def test_context_array_order_flags_a_reordered_context():
    schema = {
        "allOf": [{"$ref": "Thing.schema.json"}, {"$ref": "Person.schema.json"}],
        "@context": ["Person.schema.json", "Thing.schema.json"],
    }
    assert outcome("rule.context-array-order", schema) == "fail"
    assert "out of order" in message("rule.context-array-order", schema)


def test_context_array_order_flags_a_non_array_context():
    schema = {
        "allOf": [{"$ref": "Thing.schema.json"}, {"$ref": "Person.schema.json"}],
        "@context": {"ex": "https://example.org/"},
    }
    assert outcome("rule.context-array-order", schema) == "fail"
    assert "not an array" in message("rule.context-array-order", schema)


def test_context_array_order_flags_a_missing_target():
    schema = {
        "allOf": [{"$ref": "Thing.schema.json"}, {"$ref": "Person.schema.json"}],
        "@context": ["Thing.schema.json"],
    }
    assert outcome("rule.context-array-order", schema) == "fail"
    assert "Person.schema.json" in message("rule.context-array-order", schema)


def test_context_array_order_is_not_judged_with_fewer_than_two_refs():
    schema = {"allOf": [{"$ref": "Thing.schema.json"}], "@context": {"ex": "https://example.org/"}}
    assert outcome("rule.context-array-order", schema) == "ok"


# ------------------------------------------------------------------ OOLD-VER-534a


def test_versioned_id_should_appear_in_an_absolute_id():
    conforming = {"x-oold-version": "1.0.0", "$id": "https://example.org/schemas/1.0.0/Person.schema.json"}
    assert outcome("rule.versioned-id", conforming) == "ok"

    violating = {"x-oold-version": "1.0.0", "$id": "https://example.org/schemas/Person.schema.json"}
    assert outcome("rule.versioned-id", violating) == "warn"
    assert "1.0.0" in message("rule.versioned-id", violating)


def test_versioned_id_is_not_judged_without_both_a_version_and_an_absolute_id():
    assert outcome("rule.versioned-id", {}) == "ok"
    assert outcome("rule.versioned-id", {"x-oold-version": "1.0.0"}) == "ok"
    assert outcome("rule.versioned-id", {"x-oold-version": "1.0.0", "$id": "Person.schema.json"}) == "ok"


# ------------------------------------------------------------------ OOLD-CMP-b926


def test_a_single_root_ref_must_be_reflected_in_context():
    schema = {"allOf": [{"$ref": "Thing.schema.json"}], "@context": {"ex": "https://example.org/"}}
    assert outcome("rule.context-reflects-refs", schema) == "fail"
    assert "Thing.schema.json" in message("rule.context-reflects-refs", schema)


def test_a_single_root_ref_reflected_as_an_array_entry_is_fine():
    schema = {
        "allOf": [{"$ref": "Thing.schema.json"}],
        "@context": ["Thing.schema.json", {"ex": "https://example.org/"}],
    }
    assert outcome("rule.context-reflects-refs", schema) == "ok"


def test_a_single_root_ref_reflected_as_a_bare_string_context_is_fine():
    """A single $ref MAY be reflected by referencing it directly, with no array wrapper."""
    schema = {"allOf": [{"$ref": "Thing.schema.json"}], "@context": "Thing.schema.json"}
    assert outcome("rule.context-reflects-refs", schema) == "ok"


def test_two_or_more_refs_are_left_to_context_array_order():
    """The >= 2 case, including a target missing entirely, is rule.context-array-order's job."""
    schema = {"allOf": [{"$ref": "A.schema.json"}, {"$ref": "B.schema.json"}], "@context": {"ex": "https://x/"}}
    assert outcome("rule.context-reflects-refs", schema) == "ok"


def test_no_allof_ref_means_nothing_to_reflect():
    assert outcome("rule.context-reflects-refs", {}) == "ok"
    assert outcome("rule.context-reflects-refs", {"allOf": [{"type": "object"}]}) == "ok"


# ------------------------------------------------------------------ OOLD-CMP-1d7e


#: Two branch contexts reflected into the root, as the rule describes them. Authored as strings,
#: because that is what tells a reflected context from the schema's own object.
_REFLECTED = ["Sensor.schema.json", "Gauge.schema.json"]


def test_branch_context_conflict_flags_a_root_level_keyword_conflict():
    schema = {"@context": _REFLECTED, "oneOf": [{"$ref": "Sensor.schema.json"}, {"$ref": "Gauge.schema.json"}]}
    context = ContextView(entries=[{"reading": "ex:temperature"}, {"reading": "ex:pressure"}])
    assert outcome("rule.branch-context-conflict", schema, context) == "fail"
    assert "reading" in message("rule.branch-context-conflict", schema, context)


def test_branch_context_conflict_accepts_branches_agreeing_on_a_term():
    schema = {"@context": _REFLECTED, "anyOf": [{"$ref": "Sensor.schema.json"}, {"$ref": "Gauge.schema.json"}]}
    context = ContextView(entries=[{"reading": "ex:temperature"}, {"reading": "ex:temperature"}])
    assert outcome("rule.branch-context-conflict", schema, context) == "ok"


def test_branch_context_conflict_accepts_the_schema_overriding_an_inherited_term():
    """The specification allows a schema to append its own object to override a term it inherits.

    In the resolved view that is indistinguishable from a conflict - same term, two IRIs, two
    entries - so the check reads how each entry was authored. A string is a reflected remote
    context; a dict is the schema's own, and may override anything above it.
    """
    schema = {
        "@context": ["Sensor.schema.json", {"reading": "ex:pressure"}],
        "oneOf": [{"$ref": "Sensor.schema.json"}, {"$ref": "Gauge.schema.json"}],
    }
    context = ContextView(entries=[{"reading": "ex:temperature"}, {"reading": "ex:pressure"}])
    assert outcome("rule.branch-context-conflict", schema, context) == "ok"


def test_branch_context_conflict_is_not_judged_without_ref_branches():
    """An inline branch, like the value-form pattern's, has no remote context to conflict."""
    schema = {"anyOf": [{"type": "string"}, {"type": "object"}]}
    context = ContextView(entries=[{"reading": "ex:temperature"}, {"reading": "ex:pressure"}])
    assert outcome("rule.branch-context-conflict", schema, context) == "ok"


def test_branch_context_conflict_ignores_structural_keywords():
    """@version, @base and the like are JSON-LD machinery, not the "keyword" the rule means."""
    schema = {"oneOf": [{"$ref": "Sensor.schema.json"}, {"$ref": "Gauge.schema.json"}]}
    context = ContextView(entries=[{"@version": 1.1}, {"@version": 1.1}])
    assert outcome("rule.branch-context-conflict", schema, context) == "ok"


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
