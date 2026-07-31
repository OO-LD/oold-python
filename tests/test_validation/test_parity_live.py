"""Opt-in parity tests against a real oold-schema checkout.

These are the tests that catch drift from the reference implementation. They are skipped unless
``OOLD_SCHEMA_DIR`` points at a local checkout::

    OOLD_SCHEMA_DIR=../oold-schema uv run pytest tests/test_validation -q

The committed fixture slice is a snapshot and cannot notice upstream changes; this can. CI does
not depend on it, so the suite stays self-contained by default.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from oold.validation import Options, run_compliance, validate_directory

pytestmark = pytest.mark.parity


@pytest.fixture
def upstream(upstream_dir):
    if upstream_dir is None:
        pytest.skip("set OOLD_SCHEMA_DIR to a local oold-schema checkout to run parity tests")
    if not (upstream_dir / "examples").is_dir():
        pytest.skip(f"{upstream_dir} does not look like an oold-schema checkout")
    return upstream_dir


def _options(upstream_dir):
    """Validate against the meta-schemas the upstream checkout actually declares.

    Its examples track `main`, which can be ahead of the newest released version this package
    tracks, so pinning to `latest` would compare against the wrong rules.
    """
    return Options(meta=("remote",), offline=False)


def test_upstream_examples_pass(upstream):
    report = validate_directory(upstream / "examples", _options(upstream))
    assert report.passed, [f"{c.id} {c.target}: {c.message}" for c in report.failures()]


def test_upstream_compliance_suite_passes(upstream):
    report = run_compliance(upstream / "examples" / "compliance", _options(upstream))
    assert report.passed, [f"{c.target}: {c.message}" for c in report.failures()]


def test_vocabulary_coverage_matches_upstream(upstream):
    """Fails when oold-schema adds a keyword whose fixture this package cannot see."""
    report = run_compliance(upstream / "examples" / "compliance", _options(upstream))
    coverage = [c for c in report.checks if c.id == "coverage.vocab"]
    assert coverage and all(c.status == "ok" for c in coverage), [c.message for c in coverage]


def test_verdict_agrees_with_the_reference_harness(upstream):
    """Run `node scripts/validate.mjs` and require the same overall verdict.

    Check *counts* legitimately differ: this port splits some of the reference's combined
    sections and adds `context.predicates`. The verdict must not.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    script = upstream / "scripts" / "validate.mjs"
    if not script.is_file() or not (upstream / "node_modules").is_dir():
        pytest.skip("the reference harness is not installed (run npm install in oold-schema)")

    # S603: a fixed script inside a checkout the developer pointed us at.
    completed = subprocess.run(  # noqa: S603
        [node, str(script)],
        cwd=str(upstream),
        capture_output=True,
        text=True,
        timeout=600,
    )
    reference_passed = completed.returncode == 0

    ours = validate_directory(upstream / "examples", _options(upstream))
    theirs_compliance = run_compliance(upstream / "examples" / "compliance", _options(upstream))
    combined = ours.passed and theirs_compliance.passed

    assert combined == reference_passed, (
        f"reference exit={completed.returncode}, this port passed={combined}\n"
        f"our failures: {[f'{c.id} {c.target}: {c.message}' for c in ours.failures()]}\n"
        f"reference tail:\n{completed.stdout[-2000:]}"
    )


def test_the_reference_cannot_resolve_a_context_leaving_the_directory(upstream, remote_context_dir):
    """Documents the one capability this port adds, by demonstrating the difference.

    If upstream ever gains this ability, the divergence note in the docs is stale.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    script = upstream / "scripts" / "validate.mjs"
    if not script.is_file() or not (upstream / "node_modules").is_dir():
        pytest.skip("the reference harness is not installed")

    # S603: a fixed script inside a checkout the developer pointed us at.
    completed = subprocess.run(  # noqa: S603
        [node, str(script), str(remote_context_dir.resolve())],
        cwd=str(upstream),
        capture_output=True,
        text=True,
        timeout=600,
    )
    ours = validate_directory(remote_context_dir, Options(meta=("remote",), offline=False))

    assert ours.passed, "this port is expected to resolve a ../ context reference"
    assert completed.returncode != 0, (
        "the reference harness now resolves a context reference that leaves the directory; "
        "update the divergence note in docs/how-to/validation.md"
    )


def test_every_mapped_rule_resolves_against_the_upstream_catalog(upstream):
    """The authoritative guard against a typo in CHECK_RULES.

    Per-version coverage only warns about an unknown id, because a catalog predating a mapped
    rule is indistinguishable from a mistake. Against the *current* upstream catalog there is no
    such ambiguity: every id this package cites must exist, or reports would quote a code that
    resolves to nothing.
    """
    import json

    from oold.validation.pipeline import CHECK_RULES

    catalog = upstream / "meta" / "oold-rules.json"
    if not catalog.is_file():
        pytest.skip("upstream has not published a rule catalog yet")

    known = {r["id"] for r in json.loads(catalog.read_text(encoding="utf-8"))["rules"]}
    unknown = {check: rule for check, rule in CHECK_RULES.items() if rule not in known}
    assert not unknown, f"CHECK_RULES cites ids absent from the upstream catalog: {unknown}"
