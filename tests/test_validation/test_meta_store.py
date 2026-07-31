"""The meta-schema store: version discovery, selection, remote fetch, registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from oold.validation import meta_store
from oold.validation.meta_store import (
    META_SCHEMA_FILE,
    MetaSchemaError,
    describe_store,
    latest_version,
    load_tracked,
    resolve_selection,
    tracked_versions,
)


def test_at_least_one_version_is_tracked():
    versions = tracked_versions()
    assert versions, "the package must ship at least one meta-schema version"
    assert latest_version() == versions[-1]


def test_versions_sort_numerically_not_lexically():
    # 0.10.0 must come after 0.9.0. Sorting as strings would put it before.
    assert meta_store._version_key("0.10.0") > meta_store._version_key("0.9.0")
    assert meta_store._version_key("1.0.0") > meta_store._version_key("0.99.0")


def test_index_records_provenance_for_every_tracked_version():
    index = meta_store.load_index()
    for version in tracked_versions():
        entry = index["versions"][version]
        assert entry["tag"], f"{version} records no upstream tag"
        assert len(entry["commit"]) == 40, f"{version} records no full commit sha"


def test_recorded_checksums_match_the_shipped_files():
    """The store is curated by hand, so the checksums are what catch a bad copy."""
    index = meta_store.load_index()
    for version in tracked_versions():
        recorded = index["versions"][version].get("sha256") or {}
        for name, digest in recorded.items():
            content = (meta_store.meta_dir() / version / name).read_bytes()
            assert hashlib.sha256(content).hexdigest() == digest, f"{version}/{name} was modified"


def test_bundle_self_check_is_clean():
    bundle = load_tracked(latest_version())
    assert bundle.self_check() == []


def test_bundle_exposes_the_three_documents():
    bundle = load_tracked(latest_version())
    assert bundle.meta["$id"]
    assert bundle.ui_meta["$id"]
    assert bundle.pattern_lint["$id"]


def test_declared_keywords_are_found():
    keywords = load_tracked(latest_version()).declared_keywords()
    assert "x-oold-instance-rdf-type" in keywords
    assert any(k.startswith("x-oold-ui-") or k.startswith("x-enum-") for k in keywords)


def test_unknown_version_names_what_is_available():
    with pytest.raises(MetaSchemaError, match="not tracked"):
        load_tracked("9.9.9")


def test_selection_expands_and_deduplicates():
    latest = latest_version()
    bundles = resolve_selection(["latest", "all", latest], offline=True)
    assert [b.version for b in bundles] == tracked_versions()


def test_selection_accepts_a_bare_string():
    assert resolve_selection("latest", offline=True)[0].version == latest_version()


def test_registry_resolves_the_ui_meta_schema_cross_reference():
    """The core meta-schema $refs the UI one, so a bad registry silently stops asserting."""
    bundle = load_tracked(latest_version())
    validator = bundle.meta_validator()
    # x-oold-ui-* keywords are defined only in the UI meta-schema.
    assert validator.is_valid({"x-oold-ui-title": "ok"})
    assert not validator.is_valid({"x-oold-instance-rdf-type": "must-be-an-array"})


def test_registry_resolves_by_file_name_when_the_id_domain_differs(tmp_path, monkeypatch):
    """A released copy stamps its version into $id while $refs may still say `latest`.

    The $id domain has already moved once upstream, so the registry must not depend on any
    particular URL. This rewrites the ids and asserts validation still works.
    """
    version = latest_version()
    source = meta_store.meta_dir() / version
    target = tmp_path / "meta" / "9.9.9"
    target.mkdir(parents=True)
    for name in meta_store.meta_files():
        document = json.loads((source / name).read_text(encoding="utf-8"))
        if "$id" in document:
            document["$id"] = (
                document["$id"]
                .replace("/latest/", "/9.9.9/")
                .replace("oo-ld.github.io/oold-schema", "example.invalid/elsewhere")
            )
        (target / name).write_text(json.dumps(document), encoding="utf-8")

    monkeypatch.setattr(meta_store, "meta_dir", lambda: tmp_path / "meta")
    bundle = load_tracked("9.9.9")
    assert bundle.self_check() == []
    assert bundle.meta_validator().is_valid({"x-oold-ui-title": "still works"})


def test_describe_store_reports_versions_and_cache_state(isolated_cache):
    store = describe_store()
    assert store["latest"] == latest_version()
    assert META_SCHEMA_FILE in store["files"]
    assert store["remote"]["cached"] is False


def test_remote_is_refused_offline_when_not_cached(isolated_cache):
    with pytest.raises(MetaSchemaError, match="offline"):
        resolve_selection(["remote"], offline=True)


def test_remote_fetch_writes_only_to_the_cache(isolated_cache, monkeypatch, tmp_path):
    """A remote fetch must never touch the tracked version history."""
    documents = {
        name: json.loads((meta_store.meta_dir() / latest_version() / name).read_text("utf-8"))
        for name in meta_store.meta_files()
    }
    before = {path: path.read_bytes() for path in meta_store.meta_dir().rglob("*.json")}

    def fake_get(uri, timeout=10.0):
        return documents[uri.rsplit("/", 1)[-1]]

    monkeypatch.setattr(meta_store, "http_get_json", fake_get)
    bundle = meta_store.load_remote(offline=False)

    assert bundle.version == "remote"
    assert bundle.self_check() == []
    assert Path(meta_store.remote_cache_dir(), META_SCHEMA_FILE).is_file()
    after = {path: path.read_bytes() for path in meta_store.meta_dir().rglob("*.json")}
    assert after == before, "the tracked meta-schema folder was modified by a remote fetch"


def test_cached_remote_is_usable_offline(isolated_cache, monkeypatch):
    documents = {
        name: json.loads((meta_store.meta_dir() / latest_version() / name).read_text("utf-8"))
        for name in meta_store.meta_files()
    }
    monkeypatch.setattr(meta_store, "http_get_json", lambda uri, timeout=10.0: documents[uri.rsplit("/", 1)[-1]])
    meta_store.fetch_remote()
    # Now offline: the cached copy must satisfy the request without any fetch.
    monkeypatch.setattr(
        meta_store,
        "http_get_json",
        lambda *a, **k: pytest.fail("offline mode fetched over the network"),
    )
    assert meta_store.load_remote(offline=True).version == "remote"
