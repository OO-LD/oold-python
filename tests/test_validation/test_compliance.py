"""Guards for the compliance suite's own scaffolding, as opposed to the suite's fixtures."""

from __future__ import annotations

from oold.validation.compliance import VOCAB_PREFIXES
from oold.validation.meta_store import load_tracked, tracked_versions

#: `x-sssom` was the schema-level ontology-correspondence keyword's name before it was renamed
#: to `x-oold-sssom` for 1.0.0-rc.2 (see that version's `oold-meta-schema.json`). 1.0.0-rc.1 is
#: vendored byte-exact and keeps the old name, so it is a known, already-renamed exception rather
#: than an untracked prefix that would silently narrow vocabulary coverage.
_RENAMED_FOR_1_0_0_RC_2 = frozenset({"x-sssom"})


def _declared_x_keywords(version: str) -> set[str]:
    """Every ``x-*`` key declared directly in one version's meta-schema documents.

    Mirrors :meth:`MetaBundle.declared_keywords`'s traversal - each document's own top-level
    ``properties``, plus the UI meta-schema's keyword block - but without pre-filtering to
    ``x-oold-*``, so a keyword declared under any other prefix is still found here. That
    pre-filter is exactly what this test exists to check is not hiding anything.
    """
    bundle = load_tracked(version)
    found: set[str] = set()
    for document in bundle.documents.values():
        found.update(key for key in (document.get("properties") or {}) if key.startswith("x-"))
    ui_keywords = (bundle.ui_meta.get("$defs") or {}).get("keywords", {}).get("properties") or {}
    found.update(key for key in ui_keywords if key.startswith("x-"))
    return found


def test_vocab_prefixes_covers_every_declared_x_keyword():
    """VOCAB_PREFIXES drives vocabulary-coverage checking (see compliance.py); a keyword under a
    prefix it does not list is never counted as part of the vocabulary at all, so coverage would
    narrow silently rather than fail loudly. Nothing previously guarded that.
    """
    found: set[str] = set()
    for version in tracked_versions():
        found |= _declared_x_keywords(version)

    assert found, "the scan found no x- keywords at all, so this test would pass vacuously"

    untracked = sorted(found - _RENAMED_FOR_1_0_0_RC_2)
    untracked = [key for key in untracked if not key.startswith(VOCAB_PREFIXES)]
    assert not untracked, (
        f"{untracked} begin 'x-' but no prefix in VOCAB_PREFIXES {VOCAB_PREFIXES} covers them; "
        "an untracked prefix silently narrows vocabulary coverage"
    )
