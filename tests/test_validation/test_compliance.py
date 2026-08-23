"""Guards for the compliance suite's own scaffolding, as opposed to the suite's fixtures."""

from __future__ import annotations

from oold.validation import Options, run_compliance
from oold.validation.compliance import (
    VOCAB_EXEMPT,
    VOCAB_PREFIXES,
    declared_x_keywords,
    vocabulary_exemptions,
)
from oold.validation.meta_store import load_tracked, tracked_versions


def test_vocab_prefixes_covers_every_declared_x_keyword():
    """VOCAB_PREFIXES drives vocabulary-coverage checking (see compliance.py); a keyword under a
    prefix it does not list is never counted as part of the vocabulary at all, so coverage would
    narrow silently rather than fail loudly.

    A keyword may be left out on purpose, but only by being named in VOCAB_EXEMPT with a reason,
    which puts it in the report rather than in a reader's assumptions.
    """
    found: set[str] = set()
    for version in tracked_versions():
        found |= declared_x_keywords(load_tracked(version))

    assert found, "the scan found no x- keywords at all, so this test would pass vacuously"

    untracked = sorted(key for key in found if not key.startswith(VOCAB_PREFIXES) and key not in VOCAB_EXEMPT)
    assert not untracked, (
        f"{untracked} begin 'x-' but no prefix in VOCAB_PREFIXES {VOCAB_PREFIXES} covers them and "
        "they are not named in VOCAB_EXEMPT; an untracked prefix silently narrows vocabulary coverage"
    )


def test_every_exempt_keyword_is_actually_declared_somewhere():
    """A stale exemption is as misleading as a missing one: it implies a keyword exists that does
    not, and would keep excusing a prefix nobody ships any more.
    """
    declared: set[str] = set()
    for version in tracked_versions():
        declared |= declared_x_keywords(load_tracked(version))

    stale = sorted(key for key in VOCAB_EXEMPT if key not in declared)
    assert not stale, f"VOCAB_EXEMPT names {stale}, which no tracked meta-schema declares any more"


def test_the_coverage_report_names_what_it_left_out(compliance_dir):
    """`all N covered` must not be said while a declared keyword sits outside the count.

    1.0.0-rc.1 declares `x-sssom`, renamed to `x-oold-sssom` for the next release. It is outside
    VOCAB_PREFIXES, so it is not counted, and the report has to say so.
    """
    exempt = vocabulary_exemptions(load_tracked("1.0.0-rc.1"))
    assert "x-sssom" in exempt, "expected 1.0.0-rc.1 to declare the pre-rename keyword"

    report = run_compliance(compliance_dir, Options(meta=("1.0.0-rc.1",), offline=True))
    check = next(c for c in report.checks if c.id == "coverage.vocab")
    assert "1 exempt" in check.message and "x-sssom" in check.message, check.message
    assert not check.message.startswith("all "), "the report claimed full coverage while excluding a keyword"
    assert check.detail["exempt"] == exempt


def test_a_version_with_nothing_exempt_still_reads_plainly(compliance_dir):
    """The exemption clause must not become permanent noise on versions it does not apply to."""
    assert vocabulary_exemptions(load_tracked("1.0.0-rc.2")) == {}

    report = run_compliance(compliance_dir, Options(meta=("1.0.0-rc.2",), offline=True))
    check = next(c for c in report.checks if c.id == "coverage.vocab")
    assert check.message.startswith("all "), check.message
    assert "exempt" not in check.message
