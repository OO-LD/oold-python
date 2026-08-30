"""Opt-in parity tests against a real oold-schema corpus and the oold-js reference.

These are the tests that catch drift from the reference implementation. Two checkouts are
needed, because the corpus and the reference are separate repositories::

    OOLD_SCHEMA_DIR=../oold-schema OOLD_JS_DIR=../oold-js uv run pytest tests/test_validation -q

``OOLD_SCHEMA_DIR`` alone still runs the checks that need only the corpus; the ones that compare
verdicts skip without ``OOLD_JS_DIR``. The committed fixture slice is a snapshot and cannot
notice upstream changes; this can. CI pins the reference by tag, so a change there is adopted
deliberately rather than arriving with the next push.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

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


@pytest.fixture
def reference(upstream, reference_dir):
    """Run the oold-js validator over a directory, against the same meta-schemas this port uses.

    `--meta` points at the corpus checkout rather than anything `oold-js` ships: the reference
    vendors no meta-schemas, so both implementations read the one file set and a disagreement
    can only come from the code.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")
    if reference_dir is None:
        pytest.skip("set OOLD_JS_DIR to a local oold-js checkout to compare verdicts")
    script = reference_dir / "src" / "validate.mjs"
    if not script.is_file() or not (reference_dir / "node_modules").is_dir():
        pytest.skip("the reference harness is not installed (run npm install in oold-js)")

    def run(target: Path) -> subprocess.CompletedProcess:
        # S603: a fixed script inside a checkout the developer pointed us at.
        return subprocess.run(  # noqa: S603
            [
                node,
                str(script),
                str(Path(target).resolve()),
                "--meta",
                str((upstream / "meta").resolve()),
            ],
            cwd=str(reference_dir),
            capture_output=True,
            text=True,
            timeout=600,
        )

    return run


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


def test_verdict_agrees_with_the_reference_harness(upstream, reference):
    """Run the oold-js validator and require the same overall verdict.

    Check *counts* legitimately differ: this port splits some of the reference's combined
    sections and adds `context.predicates`. The verdict must not.
    """
    completed = reference(upstream / "examples")
    reference_passed = completed.returncode == 0

    ours = validate_directory(upstream / "examples", _options(upstream))
    theirs_compliance = run_compliance(upstream / "examples" / "compliance", _options(upstream))
    combined = ours.passed and theirs_compliance.passed

    assert combined == reference_passed, (
        f"reference exit={completed.returncode}, this port passed={combined}\n"
        f"our failures: {[f'{c.id} {c.target}: {c.message}' for c in ours.failures()]}\n"
        f"reference tail:\n{completed.stdout[-2000:]}"
    )


def test_the_reference_cannot_resolve_a_context_leaving_the_directory(reference, remote_context_dir):
    """Documents the one capability this port adds, by demonstrating the difference.

    If the reference ever gains this ability, the divergence note in the docs is stale.
    """
    completed = reference(remote_context_dir)
    ours = validate_directory(remote_context_dir, Options(meta=("remote",), offline=False))

    assert ours.passed, "this port is expected to resolve a ../ context reference"
    assert completed.returncode != 0, (
        "the reference harness now resolves a context reference that leaves the directory; "
        "update the divergence note in docs/how-to/validation.md"
    )


def test_every_mapped_rule_resolves_against_the_upstream_catalog(upstream):
    """The authoritative guard against a typo in the check registry.

    Per-version coverage only warns about an unknown id, because a catalog predating a mapped
    rule is indistinguishable from a mistake. Against the *current* upstream catalog there is no
    such ambiguity: every id this package cites must exist, or reports would quote a code that
    resolves to nothing.
    """
    import json

    from oold.validation.check_registry import rule_map

    catalog = upstream / "meta" / "oold-rules.json"
    if not catalog.is_file():
        pytest.skip("upstream has not published a rule catalog yet")

    known = {r["id"] for r in json.loads(catalog.read_text(encoding="utf-8"))["rules"]}
    unknown = {check: rule for check, rule in rule_map().items() if rule not in known}
    assert not unknown, f"the registry cites ids absent from the upstream catalog: {unknown}"
