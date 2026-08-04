"""Consumption of the upstream rule catalog.

The catalog was introduced in oold-schema after 0.8.0, so no tracked meta version ships one yet.
These tests build a synthetic version folder instead of depending on a warm remote cache, which
keeps them offline, deterministic, and honest about the shape they expect.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from oold.validation import meta_store
from oold.validation.cli import main
from oold.validation.meta_store import RULES_FILE, load_tracked
from oold.validation.pipeline import CHECK_RULES

SAMPLE_RULES = {
    "spec_version": "0.9.0",
    "rules": [
        {
            "id": "OOLD-RT-002",
            "area": "RT",
            "level": "MUST",
            "applies_to": "document",
            "section": "round-trip",
            "summary": "A strictly array-typed property must declare @container @set or @list.",
            "text": "Because the reconstruction MUST re-validate, a property that is strictly an array MUST declare @container.",
            "checkable": True,
            "since": "0.8.0",
            "deprecated": False,
        },
        {
            "id": "OOLD-INS-003",
            "area": "INS",
            "level": "MUST",
            "applies_to": "implementation",
            "section": "identity",
            "summary": "An exported identifiable entity must carry an IRI.",
            "text": "When it exports an identifiable entity it MUST assign an @id.",
            "checkable": False,
            "since": "0.8.0",
            "deprecated": False,
        },
        {
            "id": "OOLD-VER-001",
            "area": "VER",
            "level": "MUST",
            "applies_to": "document",
            "section": "identification",
            "summary": "A schema must have a $id.",
            "text": "OO-LD schemas MUST have a $id.",
            "checkable": True,
            "since": "0.8.0",
            "deprecated": False,
        },
        {
            # Nothing enforces @propagate, so this is the sample's coverage gap. It must stay
            # unenforced for the coverage tests to mean anything; if a check is ever written for
            # it, swap in another unenforced rule rather than deleting the assertions.
            "id": "OOLD-CMP-004",
            "area": "CMP",
            "level": "MUST",
            "applies_to": "document",
            "section": "merge-and-override-model",
            "summary": "A scoped context that must apply only to the immediate node sets @propagate false.",
            "text": "The schema MUST set @propagate false on that scoped context.",
            "checkable": True,
            "since": "0.8.0",
            "deprecated": False,
        },
        {
            "id": "OOLD-RT-009",
            "area": "RT",
            "level": "MUST",
            "applies_to": "document",
            "section": "round-trip",
            "summary": "A retired rule.",
            "text": "This rule MUST no longer be applied.",
            "checkable": True,
            "since": "0.8.0",
            "deprecated": True,
            "superseded_by": ["OOLD-RT-002"],
        },
    ],
}


@pytest.fixture
def catalog_version(tmp_path, monkeypatch):
    """A tracked meta version that additionally ships a rule catalog."""
    source = meta_store.meta_dir() / meta_store.latest_version()
    target = tmp_path / "meta" / "9.9.9"
    target.mkdir(parents=True)
    for name in meta_store.meta_files():
        (target / name).write_bytes((source / name).read_bytes())
    (target / RULES_FILE).write_text(json.dumps(SAMPLE_RULES), encoding="utf-8")
    (tmp_path / "meta" / "index.json").write_text(
        json.dumps({"files": meta_store.meta_files(), "versions": {"9.9.9": {}}, "remote": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(meta_store, "meta_dir", lambda: tmp_path / "meta")
    meta_store.load_index.cache_clear()
    yield "9.9.9"
    meta_store.load_index.cache_clear()


# ------------------------------------------------------------------ loading


#: Tracked versions predating the catalogue. Released tags are immutable, so these keep
#: exercising the no-catalogue path forever.
WITHOUT_CATALOG = [v for v in meta_store.tracked_versions() if not load_tracked(v).has_rules]


def test_some_tracked_version_ships_a_catalog():
    assert any(load_tracked(v).has_rules for v in meta_store.tracked_versions()), (
        "no tracked version ships oold-rules.json, so the catalogue paths are untested"
    )


def test_a_version_without_a_catalog_still_loads():
    """The catalogue postdates 0.8.0, and those tags can never gain one."""
    assert WITHOUT_CATALOG, "expected at least one pre-catalogue version to remain tracked"
    for version in WITHOUT_CATALOG:
        bundle = load_tracked(version)
        assert bundle.rules == []
        assert bundle.rule("OOLD-RT-002") is None
        assert bundle.meta_validator().is_valid({"type": "object"}), "still usable"


def test_catalog_is_loaded_when_present(catalog_version):
    bundle = load_tracked(catalog_version)
    assert bundle.has_rules
    assert bundle.rule("OOLD-RT-002")["level"] == "MUST"
    assert bundle.rule("OOLD-NOPE-001") is None


def test_a_malformed_catalog_is_treated_as_absent(catalog_version, tmp_path):
    """Rule ids annotate findings; losing them must never stop a schema being validated."""
    (tmp_path / "meta" / catalog_version / RULES_FILE).write_text("{ not json", encoding="utf-8")
    bundle = load_tracked(catalog_version)
    assert bundle.has_rules is False
    assert bundle.meta_validator().is_valid({"type": "object"})


def test_checkable_rules_exclude_implementation_advisory_and_deprecated(catalog_version):
    ids = [r["id"] for r in load_tracked(catalog_version).checkable_rules()]
    assert ids == ["OOLD-RT-002", "OOLD-VER-001", "OOLD-CMP-004"]
    assert "OOLD-INS-003" not in ids, "an implementation rule is not checkable by a validator"
    assert "OOLD-RT-009" not in ids, "a deprecated rule is not counted"


# ------------------------------------------------------------------ mapping


def test_every_mapped_rule_id_is_well_formed():
    """A typo here would make findings cite a code that resolves to nothing."""
    for check_id, rule_id in CHECK_RULES.items():
        assert rule_id.startswith("OOLD-"), f"{check_id} maps to {rule_id!r}"
        assert len(rule_id.split("-")) == 3


def test_findings_carry_no_rule_when_the_version_has_no_catalog(data_dir):
    from oold.validation import Options, validate_schema

    report = validate_schema(data_dir / "Thing.schema.json", Options(meta=(WITHOUT_CATALOG[-1],), offline=True))
    assert report.passed
    assert all(c.rule is None for c in report.checks)


def test_per_rule_checks_are_skipped_without_a_catalog(data_dir):
    """Running them blind would assert requirements the version may never have stated."""
    from oold.validation import Options, validate_schema

    report = validate_schema(data_dir / "Thing.schema.json", Options(meta=(WITHOUT_CATALOG[-1],), offline=True))
    skipped = [c for c in report.checks if c.id == "rule.checks"]
    assert skipped and skipped[0].status == "skip"
    assert "no rule catalogue" in skipped[0].message
    assert not [c for c in report.checks if c.id.startswith("rule.") and c.id != "rule.checks"]


def test_per_rule_checks_run_when_a_catalog_is_present(data_dir):
    from oold.validation import Options, validate_schema

    report = validate_schema(data_dir / "Thing.schema.json", Options(meta=("latest",), offline=True))
    ran = [c for c in report.checks if c.id.startswith("rule.") and c.id != "rule.checks"]
    assert ran, "a version with a catalogue should run the per-rule checks"
    assert all(c.rule for c in ran), "each cites the rule it enforces"


def test_findings_cite_a_rule_when_the_catalog_has_it(catalog_version, broken_dir):
    from oold.validation import Options, validate_schema

    report = validate_schema(
        broken_dir / "array_without_container.schema.json",
        Options(meta=(catalog_version,), offline=True),
    )
    container = next(c for c in report.checks if c.id == "lint.container")
    assert container.rule == "OOLD-RT-002"
    # lint.pattern maps to a rule this sample catalog does not contain, so it stays uncited
    # rather than quoting a dangling code.
    assert next(c for c in report.checks if c.id == "lint.pattern").rule is None


def test_rule_appears_in_the_serialised_report(catalog_version, broken_dir):
    from oold.validation import Options, validate_schema

    report = validate_schema(
        broken_dir / "array_without_container.schema.json",
        Options(meta=(catalog_version,), offline=True),
    )
    payload = report.to_dict("summary")
    cited = [c for c in payload["checks"] if c.get("rule")]
    assert any(c["rule"] == "OOLD-RT-002" for c in cited)


# ------------------------------------------------------------------ coverage


def test_coverage_is_skipped_when_the_version_ships_no_catalog(compliance_dir):
    from oold.validation import Options, run_compliance

    report = run_compliance(compliance_dir, Options(meta=(WITHOUT_CATALOG[-1],), offline=True))
    coverage = [c for c in report.checks if c.id == "coverage.rules"]
    assert coverage and coverage[0].status == "skip"


def test_unenforced_rules_are_a_warning_not_a_failure(catalog_version, compliance_dir):
    """The gap is what the catalog exists to show; failing on it would block every run."""
    from oold.validation import Options, run_compliance

    report = run_compliance(compliance_dir, Options(meta=(catalog_version,), offline=True))
    coverage = next(c for c in report.checks if c.id == "coverage.rules")
    assert coverage.status == "warn"
    assert "OOLD-CMP-004" in coverage.detail["unenforced"]


def test_a_mapped_rule_missing_from_an_older_catalog_is_not_a_failure(catalog_version, compliance_dir):
    """A catalog predating a mapped rule is indistinguishable from a typo, so it only warns.

    The sample catalog omits OOLD-RT-001, which CHECK_RULES maps to. Failing there would break
    validation against any meta version older than the newest rule this package enforces.
    """
    from oold.validation import Options, run_compliance

    report = run_compliance(compliance_dir, Options(meta=(catalog_version,), offline=True))
    coverage = next(c for c in report.checks if c.id == "coverage.rules")
    assert coverage.status == "warn"
    assert "OOLD-RT-001" in coverage.detail["unknown"]
    assert report.passed, "an older catalog must not fail the run"


# ------------------------------------------------------------------ CLI


@pytest.fixture
def run():
    runner = CliRunner()
    return lambda *args: runner.invoke(main, list(args), catch_exceptions=False)


def test_rules_list(run, catalog_version):
    result = run("rules", "list", "--meta", catalog_version)
    assert result.exit_code == 0
    assert "OOLD-RT-002" in result.output
    assert "lint.container" in result.output, "the enforcing check is shown"


def test_rules_list_filters_by_area(run, catalog_version):
    out = run("rules", "list", "--meta", catalog_version, "--area", "VER").output
    assert "OOLD-VER-001" in out
    assert "OOLD-RT-002" not in out


def test_rules_list_unchecked_shows_the_gap(run, catalog_version):
    out = run("rules", "list", "--meta", catalog_version, "--unchecked").output
    assert "OOLD-CMP-004" in out, "no check enforces @propagate"
    assert "OOLD-RT-002" not in out, "lint.container enforces it"
    assert "OOLD-VER-001" not in out, "rule.id enforces it"


def test_rules_explain(run, catalog_version):
    out = run("rules", "explain", "OOLD-RT-002", "--meta", catalog_version).output
    assert "MUST" in out
    assert "enforced by lint.container" in out
    assert "#rule-OOLD-RT-002" in out
    assert "MUST re-validate" in out, "the specification text is shown"


def test_rules_explain_is_case_insensitive(run, catalog_version):
    assert run("rules", "explain", "oold-rt-002", "--meta", catalog_version).exit_code == 0


def test_rules_explain_unknown_id_suggests_listing(run, catalog_version):
    result = run("rules", "explain", "OOLD-NOPE-001", "--meta", catalog_version)
    assert result.exit_code != 0
    assert "oold rules list" in result.output


def test_rules_command_explains_a_missing_catalog(run):
    """The common case today: no released version ships one yet."""
    result = run("rules", "list", "--meta", WITHOUT_CATALOG[-1], "--offline")
    assert result.exit_code != 0
    assert "no rule catalog" in result.output
    assert "remote" in result.output, "the message points at where a catalog can be found"
