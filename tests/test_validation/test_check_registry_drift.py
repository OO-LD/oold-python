"""The four tests that hold the check registry to what the validator actually does.

`test_check_registry.py` exercises the ten self-contained `rule.*` predicates in isolation. These
run the fixture corpus end to end instead, and compare what came out against what
`check_registry.CHECKS` claims exists. See `docs/architecture.md`, "Validation subsystem design",
for the design these four tests implement.
"""

from __future__ import annotations

from pathlib import Path

from oold.validation import Options, run_compliance, validate_directory, validate_instance
from oold.validation.check_registry import CHECKS
from oold.validation.meta_store import load_tracked, tracked_versions
from oold.validation.report import SKIP

#: One version with no rule catalogue and the newest tracked one, which has one. That is enough
#: to surface every id the pipeline can emit; adding more tracked versions would only slow the
#: suite down for no extra coverage. The newest is read rather than named: written out, it stops
#: being the newest the next time a version is vendored, and the drift these tests exist to catch
#: would then be measured against a stale catalogue without anything saying so.
_CORPUS_META = ("0.7.0", tracked_versions()[-1])

#: These two fire only on an infrastructure failure path the corpus cannot exercise without
#: corrupting something every other test relies on: a broken vendored meta-schema
#: (`meta.self-check`, and those files must stay byte-exact - see
#: `docs/maintaining-meta-schemas.md`) or an unreadable compliance fixture file
#: (`compliance.suite`, and corrupting one would also break every test that expects the
#: compliance suite to run cleanly). Exempted from test 2 rather than faked with a fixture that
#: would compromise something else.
_ONLY_ON_FAILURE_PATHS = frozenset({"meta.self-check", "compliance.suite"})


def _emitted_ids(data_dir: Path, broken_dir: Path, compliance_dir: Path) -> set[str]:
    """Every check id the validator emits across the whole fixture corpus."""
    opts = Options(meta=_CORPUS_META, offline=True)
    ids: set[str] = set()
    for report in (
        validate_directory(data_dir, opts),
        run_compliance(compliance_dir, opts),
        validate_directory(broken_dir, opts),
        validate_instance(data_dir / "PersonWithPet.instance.json", options=opts),
    ):
        ids |= {c.id for c in report.checks}
    return ids


def _normalize(check_id: str) -> str:
    """Fold `compliance.<kind>` down to the one family entry the registry carries.

    The id is built as ``f"compliance.{case.kind}"`` from fixture data rather than from code, so
    a new case kind in a compliance fixture must not need a new registry entry. `compliance.suite`
    is a literal id, not data-derived, and is left alone.
    """
    if check_id.startswith("compliance.") and check_id not in {"compliance.suite", "compliance.*"}:
        return "compliance.*"
    return check_id


# ------------------------------------------------------------------ 1. every emitted id is registered


def test_every_emitted_id_is_registered(data_dir, broken_dir, compliance_dir):
    """Adding a check without registering it fails, naming the id."""
    emitted = {_normalize(c) for c in _emitted_ids(data_dir, broken_dir, compliance_dir)}
    registered = {c.id for c in CHECKS}
    unregistered = sorted(emitted - registered)
    assert not unregistered, (
        f"the validator emitted check id(s) with no entry in check_registry.CHECKS: {unregistered} "
        "- add a CheckInfo for each id, or fix the emission site if it was a typo"
    )


# ------------------------------------------------------------------ 2. every registered id is emitted


def test_every_registered_id_is_emitted(data_dir, broken_dir, compliance_dir):
    """Catches a stale entry, and a check that silently stopped running."""
    emitted = {_normalize(c) for c in _emitted_ids(data_dir, broken_dir, compliance_dir)}
    missing = sorted(check.id for check in CHECKS if check.id not in emitted and check.id not in _ONLY_ON_FAILURE_PATHS)
    assert not missing, (
        f"check_registry.CHECKS has entries the fixture corpus never produced: {missing} - either "
        "the check silently stopped running, or the entry is stale and should be removed"
    )


# ------------------------------------------------------------------ 3. every named rule exists somewhere


def test_every_named_rule_exists_in_some_vendored_catalogue():
    """Catches a typo'd or retired rule id, against every tracked version at once."""
    known: set[str] = set()
    for version in tracked_versions():
        known |= {rule["id"] for rule in load_tracked(version).rules}

    unknown = sorted(f"{check.id} cites {check.rule}" for check in CHECKS if check.rule and check.rule not in known)
    assert not unknown, (
        f"check(s) name a rule absent from every vendored catalogue: {unknown} - fix the typo, or "
        "vendor the meta-schema version that introduces the rule"
    )


# ------------------------------------------------------------------ 4. predates_catalog gating


def test_predates_catalog_is_exactly_what_runs_under_a_pre_catalogue_version(data_dir, broken_dir):
    """0.7.0 ships no rule catalogue. A check must run there if, and only if, it predates one.

    Pins the backward-compatibility promise to a test rather than to reviewer memory. Both
    directions fail loudly, which is what stops a new rule-carrying check from quietly judging a
    specification version it was never written against.
    """
    opts = Options(meta=("0.7.0",), offline=True)
    # A gated check is not absent from the report: it emits a SKIP saying why. So "did it run"
    # has to mean "reached a verdict", not "appears somewhere". Counting SKIP as having run makes
    # the silently_skipped direction below vacuous, since a check that wrongly stands down still
    # shows up - which is the exact regression this test exists to catch.
    ran = {c.id for c in validate_directory(data_dir, opts).checks if c.status != SKIP}
    ran |= {c.id for c in validate_directory(broken_dir, opts).checks if c.status != SKIP}

    rule_carrying = [check for check in CHECKS if check.rule]
    should_run = {check.id for check in rule_carrying if check.predates_catalog}
    should_skip = {check.id for check in rule_carrying if not check.predates_catalog}

    silently_skipped = sorted(should_run - ran)
    assert not silently_skipped, (
        f"check(s) marked predates_catalog=True reached no verdict under --meta 0.7.0, which "
        f"ships no rule catalogue - they encode requirements older than the catalogue and must "
        f"still be enforced there, but they only skipped: {silently_skipped}"
    )

    wrongly_run = sorted(should_skip & ran)
    assert not wrongly_run, (
        f"check(s) with predates_catalog=False (the default) produced a finding under --meta "
        f"0.7.0, which ships no rule catalogue - they must be skipped as part of the rule.* "
        f"family instead: {wrongly_run}"
    )
