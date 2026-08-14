"""End-to-end pipeline behaviour, including that the broken fixtures actually fail."""

from __future__ import annotations

import pytest

from oold.validation import Options, run_compliance, validate_directory, validate_instance, validate_schema
from oold.validation.report import FAIL, OK, SKIP, WARN

OFFLINE = Options(meta=("latest",), offline=True)


def _ids(report, status=None):
    return {c.id for c in report.checks if status is None or c.status == status}


# ------------------------------------------------------------------ the good path


def test_the_committed_slice_passes_completely(data_dir):
    report = validate_directory(data_dir, OFFLINE)
    assert report.passed, [f"{c.id} {c.target}: {c.message}" for c in report.failures()]
    assert report.counts[FAIL] == 0


def test_every_expected_check_runs_over_the_slice(data_dir):
    """A check that silently stops running would otherwise look like a clean pass."""
    report = validate_directory(data_dir, OFFLINE)
    assert _ids(report) >= {
        "schema.meta",
        "schema.refs",
        "lint.pattern",
        "lint.container",
        "generate.satisfiable",
        "roundtrip.generated",
        "context.remote",
        "context.predicates",
        "variants",
        "instance.schema",
        "roundtrip.instance",
    }


def test_a_single_schema_can_be_validated(data_dir):
    report = validate_schema(data_dir / "PersonWithPet.schema.json", OFFLINE)
    assert report.passed
    assert report.targets() == ["PersonWithPet.schema.json"]


def test_an_instance_is_validated_against_the_schema_it_names(data_dir):
    report = validate_instance(data_dir / "PersonWithPet.instance.json", options=OFFLINE)
    assert report.passed
    assert _ids(report) == {"instance.schema", "roundtrip.instance"}


def test_roundtrip_reports_triples_and_method(data_dir):
    report = validate_instance(data_dir / "PersonWithPet.instance.json", options=OFFLINE)
    check = next(c for c in report.checks if c.id == "roundtrip.instance")
    assert check.detail["method"] == "framed"
    assert check.detail["triples"] == 3


def test_a_context_chain_leaving_the_directory_resolves(remote_context_dir):
    """The capability the reference harness lacks: its loader only maps its own directory."""
    report = validate_schema(remote_context_dir / "Leaf.schema.json", OFFLINE)
    assert report.passed, [f"{c.id}: {c.message}" for c in report.failures()]
    assert "context.remote" in _ids(report, OK)


# ------------------------------------------------------------------ the broken fixtures


@pytest.mark.parametrize(
    "fixture,check_id,status",
    [
        ("invalid_meta.schema.json", "schema.meta", FAIL),
        ("missing_context_term.schema.json", "roundtrip.generated", FAIL),
        ("undefined_prefix.schema.json", "context.predicates", FAIL),
        ("unresolvable_context_ref.schema.json", "context.predicates", FAIL),
        ("xsd_string_coercion.schema.json", "lint.pattern", FAIL),
        ("array_without_container.schema.json", "lint.container", FAIL),
        # These two exist because their predicates returned before evaluating anything on the
        # rest of the corpus: no other fixture pins a `type` alongside x-oold-instance-rdf-type,
        # and none closes its objects. Both checks passed by never running.
        ("inline_type_disagrees.schema.json", "rule.instance-type", FAIL),
        ("closed_object_rejects_metadata.schema.json", "rule.closed-object", FAIL),
        # lint.iri-format only ever warns, so this one does not make the report fail overall.
        ("iri_reference_without_format.schema.json", "lint.iri-format", WARN),
        # Likewise rule.base-alignment: OOLD-CMP-53bf is a SHOULD. This fixture exists because
        # no other schema in the corpus declares @base, so without it the predicate is never
        # reached through the pipeline and would pass by never running.
        ("base_uri_misaligned.schema.json", "rule.base-alignment", WARN),
        ("legacy_dialect.schema.json", "rule.dialect-version", FAIL),
        # No other fixture composes two or more allOf/$ref members, so without this one
        # rule.context-array-order's >= 2 branch is never reached through the pipeline.
        ("context_array_order_mismatch.schema.json", "rule.context-array-order", FAIL),
        # No other fixture combines x-oold-version with an absolute $id, so without this one
        # rule.versioned-id's comparison is never reached through the pipeline.
        ("versioned_id_missing_version.schema.json", "rule.versioned-id", WARN),
        # Every other fixture with a single allOf $ref reflects it, so without this one
        # rule.context-reflects-refs never reaches its failing branch through the pipeline.
        ("root_ref_not_reflected.schema.json", "rule.context-reflects-refs", FAIL),
        # No other fixture composes oneOf/anyOf branches by $ref, so without this one
        # rule.branch-context-conflict's comparison is never reached through the pipeline.
        ("branch_context_conflict.schema.json", "rule.branch-context-conflict", FAIL),
        # No fixture in the main corpus reuses a property name across an allOf ancestor chain
        # (Researcher/Person/Thing never repeat one), so without this one rule.narrow-only's
        # per-keyword comparison is never reached through the pipeline.
        ("narrow_only_relaxation.schema.json", "rule.narrow-only", FAIL),
    ],
)
def test_each_broken_fixture_fails_the_check_it_targets(broken_dir, fixture, check_id, status):
    """Proves the checks fire, rather than only that valid input passes."""
    report = validate_schema(broken_dir / fixture, OFFLINE)
    if status == FAIL:
        assert not report.passed, f"{fixture} was expected to fail"
    assert check_id in _ids(report, status), (
        f"{fixture}: expected {check_id} at {status}, got: {[(c.id, c.status, c.message) for c in report.checks]}"
    )


def test_undefined_prefix_is_reported_as_suspicious_not_dropped(broken_dir):
    report = validate_schema(broken_dir / "undefined_prefix.schema.json", OFFLINE)
    check = next(c for c in report.checks if c.id == "context.predicates")
    assert check.status == FAIL
    assert check.detail["suspicious"] == {"latitude": "schema:latitude"}


def test_missing_context_term_names_the_orphan_property(broken_dir):
    report = validate_schema(broken_dir / "missing_context_term.schema.json", OFFLINE)
    failures = {c.id: c for c in report.failures()}
    assert "orphan" in failures["roundtrip.generated"].message
    assert failures["context.predicates"].detail["dropped"] == ["orphan"]


# ------------------------------------------------------------------ meta versions


def test_only_version_dependent_checks_are_tagged_with_a_version(data_dir):
    """Fanning every check across versions would multiply the report for no information.

    Three families legitimately depend on the version: the two driven by a meta-schema, and the
    per-rule checks, whose applicability and severity come from that version's catalogue.
    Everything else - $ref resolution, generation, round-trip - runs once.
    """
    report = validate_directory(data_dir, OFFLINE)
    tagged = {c.id for c in report.checks if c.meta_version}
    untagged = {c.id for c in report.checks if not c.meta_version}

    assert {"schema.meta", "lint.pattern"} <= tagged
    assert all(c in {"schema.meta", "lint.pattern"} or c.startswith("rule.") for c in tagged), tagged
    assert not any(c.startswith("rule.") for c in untagged), untagged
    for once in ("schema.refs", "generate.satisfiable", "roundtrip.generated"):
        assert once in untagged


def test_multiple_versions_only_repeat_the_dependent_checks(data_dir, monkeypatch):
    from oold.validation import meta_store

    latest = meta_store.latest_version()
    single = validate_directory(data_dir, Options(meta=(latest,), offline=True))
    # Selecting the same version twice must deduplicate rather than double the work.
    twice = validate_directory(data_dir, Options(meta=(latest, "latest"), offline=True))
    assert len(single.checks) == len(twice.checks)


def test_unknown_meta_version_is_a_fatal_error_not_a_traceback(data_dir):
    report = validate_directory(data_dir, Options(meta=("9.9.9",), offline=True))
    assert report.fatal_error and "not tracked" in report.fatal_error
    assert not report.passed


def test_offline_without_a_cached_remote_explains_itself(data_dir, isolated_cache):
    report = validate_directory(data_dir, Options(meta=("remote",), offline=True))
    assert report.fatal_error and "offline" in report.fatal_error


# ------------------------------------------------------------------ filtering and errors


def test_checks_can_be_filtered(data_dir):
    report = validate_directory(data_dir, Options(meta=("latest",), offline=True, only=("schema.",)))
    assert _ids(report) == {"schema.meta", "schema.refs"}


def test_checks_can_be_skipped(data_dir):
    report = validate_directory(data_dir, Options(meta=("latest",), offline=True, skip=("roundtrip.", "variants")))
    assert not {i for i in _ids(report) if i.startswith("roundtrip.")}


def test_a_missing_directory_is_reported(tmp_path):
    report = validate_directory(tmp_path / "nope", OFFLINE)
    assert report.fatal_error and "not a directory" in report.fatal_error


def test_an_empty_directory_is_reported(tmp_path):
    report = validate_directory(tmp_path, OFFLINE)
    assert report.fatal_error and "no *" in report.fatal_error


def test_an_instance_without_a_schema_reference_is_reported(tmp_path):
    (tmp_path / "x.instance.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path / "y.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    report = validate_directory(tmp_path, OFFLINE)
    check = next(c for c in report.checks if c.id == "instance.schema")
    assert check.status == FAIL and "$schema" in check.message


# ------------------------------------------------------------------ compliance


def test_the_compliance_suite_passes(compliance_dir):
    """The fixtures and the tracked meta-schema are both snapshots of the same release.

    That consistency is the point: the lint rules a fixture asserts only exist in the version
    that introduced them, so mixing a newer fixture set with an older meta-schema produces
    failures that say nothing about this code. Upstream's current state is covered separately
    by the opt-in parity tests, which use `--meta remote`.
    """
    report = run_compliance(compliance_dir, OFFLINE)
    assert report.passed, [f"{c.target}: {c.message}" for c in report.failures()]


def test_vocabulary_coverage_is_checked(compliance_dir):
    report = run_compliance(compliance_dir, OFFLINE)
    coverage = [c for c in report.checks if c.id == "coverage.vocab"]
    assert coverage and coverage[0].status == OK, "every meta-schema keyword needs a fixture"


def test_compliance_on_a_missing_directory_is_reported(tmp_path):
    report = run_compliance(tmp_path / "nope", OFFLINE)
    assert report.fatal_error


# ------------------------------------------------------------------ report shape


def test_report_serialises_at_both_verbosities(data_dir):
    report = validate_schema(data_dir / "Thing.schema.json", OFFLINE)
    summary = report.to_dict("summary")
    full = report.to_dict("full")
    assert summary["passed"] is True
    assert summary["summary"]["checks"] == len(report.checks)
    assert any("detail" in c for c in full["checks"])
    assert not any("detail" in c for c in summary["checks"])


def test_warnings_do_not_fail_a_run():
    from oold.validation.report import Report

    report = Report(source="x")
    report.add("lint.iri-format", "a.schema.json", WARN, "recommendation")
    report.add("schema.meta", "a.schema.json", SKIP, "skipped")
    assert report.passed
    report.add("schema.meta", "a.schema.json", FAIL, "broken")
    assert not report.passed
