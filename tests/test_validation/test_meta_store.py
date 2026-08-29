"""The meta-schema store: version discovery, selection, remote fetch, registry."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from referencing import Registry

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
from oold.validation.resolve import SchemaResolutionError


def test_at_least_one_version_is_tracked():
    versions = tracked_versions()
    assert versions, "the package must ship at least one meta-schema version"
    assert latest_version() == versions[-1]


def test_versions_sort_numerically_not_lexically():
    # 0.10.0 must come after 0.9.0. Sorting as strings would put it before.
    assert meta_store._version_key("0.10.0") > meta_store._version_key("0.9.0")
    assert meta_store._version_key("1.0.0") > meta_store._version_key("0.99.0")


def test_a_pre_release_sorts_before_its_own_release():
    """`latest` must never resolve to a release candidate over the release itself.

    Splitting on "." alone put `1.0.0-rc.1` *after* `1.0.0`, because the chunk "0-rc" is not a
    digit and fell to the string branch. Vendoring both would then have made every default run
    validate against the candidate.
    """
    k = meta_store._version_key
    assert k("1.0.0-rc.1") < k("1.0.0")
    assert k("1.0.0-rc.1") < k("1.0.0-rc.2")
    assert k("0.9.0") < k("1.0.0-rc.1")
    assert k("1.0.0") < k("2.0.0-alpha.1")


def test_full_ordering_including_pre_releases():
    unsorted = ["1.0.0", "0.7.0", "1.0.0-rc.2", "0.10.0", "1.0.0-rc.1", "0.9.0"]
    assert sorted(unsorted, key=meta_store._version_key) == [
        "0.7.0",
        "0.9.0",
        "0.10.0",
        "1.0.0-rc.1",
        "1.0.0-rc.2",
        "1.0.0",
    ]


def test_index_records_provenance_for_every_tracked_version():
    index = meta_store.load_index()
    for version in tracked_versions():
        entry = index["versions"][version]
        assert entry["tag"], f"{version} records no upstream tag"
        assert len(entry["commit"]) == 40, f"{version} records no full commit sha"


def test_recorded_checksums_match_the_shipped_files():
    """The store is curated by hand, so the checksums are what catch a bad copy.

    Two things have broken this in practice, and both are worth naming in the failure message
    because neither is obvious from a hash mismatch: a JSON-formatting pre-commit hook rewriting
    the file, and git's `core.autocrlf` converting line endings on checkout. `.gitattributes`
    marks these paths `-text` and `.pre-commit-config.yaml` excludes them; if either is lost,
    this test is what notices.
    """
    index = meta_store.load_index()
    for version in tracked_versions():
        recorded = index["versions"][version].get("sha256") or {}
        for name, digest in recorded.items():
            content = (meta_store.meta_dir() / version / name).read_bytes()
            assert hashlib.sha256(content).hexdigest() == digest, (
                f"{version}/{name} no longer matches the sha256 recorded in meta/index.json. "
                "It is a verbatim copy of an oold-schema release tag, so either it was edited, "
                "a formatting hook rewrote it, or git converted its line endings "
                "(check .gitattributes marks it -text)."
            )


def test_the_vendored_files_are_stored_with_unix_line_endings():
    """Recorded checksums are of LF bytes, so a CRLF copy passes here and fails on Linux.

    The checksum test above compares against the working tree. On Windows with `core.autocrlf`
    that hides the very mistake it exists to catch: a file committed with CRLF hashes one way in
    a Windows checkout and another in a Linux one, so the suite is green locally and red in CI.
    Asserting the bytes directly is platform-independent - the file either has CRLF in it or it
    does not - which makes this the check that actually travels.
    """
    for version in tracked_versions():
        for path in sorted((meta_store.meta_dir() / version).glob("*.json")):
            assert b"\r\n" not in path.read_bytes(), (
                f"{version}/{path.name} contains CRLF. Vendored files are copied verbatim from an "
                "oold-schema tag and must stay LF, because meta/index.json records a sha256 of "
                "their bytes. Convert it back to LF and re-check the recorded digest."
            )


def test_bundle_self_check_is_clean():
    bundle = load_tracked(latest_version())
    assert bundle.self_check() == []


def test_the_newest_version_vendors_a_schema_for_its_rule_catalogue():
    """Without it the catalogue is data the validator trusts with nothing checking it."""
    bundle = load_tracked(latest_version())
    assert bundle.rules, "the newest tracked version should ship a rule catalogue"
    assert bundle.rules_schema, "and the schema describing it, vendored from the same source"


def test_a_damaged_catalogue_is_reported_rather_than_read_as_a_shorter_specification():
    """The failure this schema exists for, and the reason it is not merely nice to have.

    A truncated catalogue is indistinguishable from a specification that states fewer rules: the
    checks enforcing the missing ones skip, each saying the version never stated its rule, and the
    run passes. Every one of those messages is false. `meta.self-check` is what contradicts them.
    """
    bundle = load_tracked(latest_version())
    damaged = json.loads(json.dumps(bundle.rules_document))
    damaged["rules"] = damaged["rules"][:5]
    damaged["rules"][0]["text_sha256"] = "deadbeef"

    problems = bundle.model_copy(update={"rules_document": damaged})._catalog_problems()
    assert problems, "a corrupted catalogue passed self-check"
    assert any("text_sha256" in p for p in problems), problems


def test_an_unreadable_catalogue_is_reported_not_swallowed(tmp_path):
    """Loading stays lenient so validation continues; the problem surfaces as a finding."""
    (tmp_path / meta_store.RULES_FILE).write_text("{ not json", encoding="utf-8")
    catalog, error = meta_store._read_rules(tmp_path)
    assert catalog is None
    assert error and meta_store.RULES_FILE in error


def test_an_unreadable_rules_schema_is_reported_not_swallowed(tmp_path):
    """A corrupt schema must not be indistinguishable from an absent one.

    Absent means "this version predates the catalog schema", and `_catalog_problems` correctly
    validates nothing. Corrupt means the file the catalog is checked against is broken, and
    returning None for both sent that case down the same path - so a broken schema disabled
    catalog validation entirely, reporting nothing. The catalog is data the validator trusts,
    which is exactly why its own checking must not fail open.
    """
    (tmp_path / meta_store.RULES_SCHEMA_FILE).write_text("{ not json", encoding="utf-8")
    schema, error = meta_store._read_rules_schema(tmp_path)
    assert schema is None
    assert error and meta_store.RULES_SCHEMA_FILE in error

    # And it reaches the caller, rather than stopping at the loader.
    bundle = meta_store.MetaBundle(
        version="test",
        origin=str(tmp_path),
        registry=Registry(),
        documents={},
        rules_document={"rules": []},
        rules_schema_error=error,
    )
    assert bundle._catalog_problems() == [error]


def test_an_absent_rules_schema_stays_silent(tmp_path):
    """The other half of the distinction: a version that never vendored one is not a defect."""
    schema, error = meta_store._read_rules_schema(tmp_path)
    assert schema is None and error is None


def test_a_malformed_catalog_is_treated_as_absent():
    """Entries that do not parse as `Rule` must not crash a run or half-populate `bundle.rules`.

    Mirrors `test_an_unreadable_catalogue_is_reported_not_swallowed` one level up: there the file
    itself could not be read, here it reads fine as JSON but its entries do not match `Rule`'s
    shape. Both must be treated the same way - no rules, and a reason recorded for
    `MetaBundle.self_check` to report - rather than raising or silently keeping the entries that
    do happen to parse.
    """
    catalog = {"spec_version": "9.9.9", "rules": [{"id": "OOLD-VER-0000"}]}  # missing every other field
    rules, error = meta_store._parse_rules(catalog, None)
    assert rules == []
    assert error and meta_store.RULES_FILE in error


def test_a_rule_entry_missing_level_is_rejected_at_parse_time():
    """Closes the hazard at its source: `check_registry.severity()` reads `rule.level` and falls
    back to WARN when it is absent, so a rule missing that field must fail to parse rather than
    quietly becoming a rule nothing can ever fail against.
    """
    entry = {
        "id": "OOLD-VER-0000",
        "area": "VER",
        # "level" is deliberately omitted.
        "applies_to": "document",
        "section": "x",
        "summary": "x",
        "text": "x",
        "text_sha256": "0" * 64,
        "machine_checkable": True,
        "since": "1.0.0",
        "deprecated": False,
        "source": "x:1",
    }
    with pytest.raises(ValidationError):
        meta_store.Rule.model_validate(entry)


def test_the_rule_model_requires_exactly_what_the_vendored_schema_requires():
    """Ties `Rule`'s required fields to the vendored `oold-rules.schema.json`'s, for every version
    that ships one, so an upstream rename or drop of a required field (`level` above all - see
    `check_registry.severity`) fails this test loudly instead of silently downgrading every MUST
    to a warning.
    """
    checked_any = False
    for version in tracked_versions():
        schema, schema_error = meta_store._read_rules_schema(meta_store.meta_dir() / version)
        assert schema_error is None, schema_error
        if schema is None:
            continue
        checked_any = True
        expected = set(schema["$defs"]["rule"]["required"])
        actual = {name for name, info in meta_store.Rule.model_fields.items() if info.is_required()}
        assert actual == expected, (
            f"{version}/{meta_store.RULES_SCHEMA_FILE} requires {sorted(expected)} for a rule "
            f"entry, but meta_store.Rule requires {sorted(actual)}. A silent mismatch here is "
            "exactly the hazard this test exists to catch: check_registry.severity() reads "
            "rule.level, and a renamed or dropped required field must fail loudly here rather "
            "than let severity() fall back to WARN unnoticed."
        )
    assert checked_any, "no tracked version vendors oold-rules.schema.json, so this test checked nothing"


def test_a_version_without_a_catalogue_schema_still_loads():
    """0.7.0 and 0.8.0 predate both files. Absence is the older layout, not a defect."""
    for version in tracked_versions():
        bundle = load_tracked(version)
        if bundle.rules_schema is None:
            assert bundle.self_check() == [], f"{version} must load clean without a catalogue schema"


def test_the_fixture_slice_records_the_release_it_came_from():
    """The tag is data, and it belongs beside the other provenance rather than in prose.

    The fixture directory's own README used to claim v0.8.0 for a full release after the slice
    had already moved to v1.0.0-rc.1, because a vendoring updated the files and not the sentence
    describing them. A compliance fixture asserts the rules of the version that introduced it, so
    a slice and a meta-schema from different releases produce failures that say nothing about
    this code.
    """
    fixtures = meta_store.load_index()["fixtures"]
    assert fixtures["tag"] == f"v{tracked_versions()[-1]}", (
        "tests/data/oold/ and the newest tracked meta-schema version must come from one release; "
        "refresh the slice (see docs/maintaining-meta-schemas.md) or vendor the matching version"
    )


def test_bundle_exposes_every_document_the_version_ships():
    bundle = load_tracked(latest_version())
    assert bundle.meta["$id"]
    assert bundle.ui_meta["$id"]
    assert bundle.pattern_lint["$id"]
    # Not three since 1.0.0-rc.2: the dialect is a wrapper plus the base it $refs, and the base
    # has no accessor of its own because nothing reaches it except through that $ref.
    assert set(bundle.documents) == set(meta_store.meta_files(latest_version()))


def test_declared_keywords_are_found():
    keywords = load_tracked(latest_version()).declared_keywords()
    assert "x-oold-instance-rdf-type" in keywords
    assert any(k.startswith("x-oold-ui-") or k.startswith("x-enum-") for k in keywords)


def test_unknown_version_names_what_is_available():
    with pytest.raises(MetaSchemaError, match="not tracked"):
        load_tracked("9.9.9")


def test_selection_deduplicates_and_keeps_selector_order():
    """Selectors are honoured in the order given, not re-sorted by version.

    `--meta 0.8.0 --meta 0.7.0` should report in that order, because the caller chose it. So
    `latest` first then `all` puts the newest first and backfills the rest, which is the
    documented contract rather than an accident.
    """
    latest = latest_version()
    bundles = resolve_selection(["latest", "all", latest], offline=True)
    versions = [b.version for b in bundles]
    assert versions[0] == latest
    assert sorted(versions) == sorted(tracked_versions())
    assert len(versions) == len(set(versions))


def test_all_on_its_own_is_in_version_order():
    assert [b.version for b in resolve_selection(["all"], offline=True)] == tracked_versions()


def test_explicit_order_is_preserved():
    versions = tracked_versions()
    if len(versions) < 2:
        pytest.skip("needs at least two tracked versions")
    reverse = list(reversed(versions))
    assert [b.version for b in resolve_selection(reverse, offline=True)] == reverse


def test_selection_accepts_a_bare_string():
    assert resolve_selection("latest", offline=True)[0].version == latest_version()


def test_registry_resolves_the_ui_meta_schema_cross_reference():
    """The core meta-schema $refs the UI one, so a bad registry silently stops asserting."""
    bundle = load_tracked(latest_version())
    validator = bundle.meta_validator()
    # Every probe carries $id because the dialect requires one of a document from 1.0.0-rc.2 on.
    # Without it these assertions pass or fail for a reason that has nothing to do with the
    # registry.
    probe = {"$id": "https://example.org/probe.schema.json"}
    # The keyword has to be one the UI meta-schema constrains, and the probe has to violate that
    # constraint. Merely naming an x-oold-ui-* keyword proves nothing: 2020-12 tolerates an
    # unreached keyword as an annotation, so such a probe is valid whether or not the
    # cross-reference resolved. x-oold-ui-form-hidden is declared boolean, and only there.
    assert validator.is_valid(probe | {"x-oold-ui-form-hidden": True})
    assert not validator.is_valid(probe | {"x-oold-ui-form-hidden": "not-a-boolean"})
    assert not validator.is_valid(probe | {"x-oold-instance-rdf-type": "must-be-an-array"})


def test_registry_resolves_by_file_name_when_the_id_domain_differs(tmp_path, monkeypatch):
    """A released copy stamps its version into $id while $refs may still say `latest`.

    The $id domain has already moved once upstream, so the registry must not depend on any
    particular URL. This rewrites the ids and asserts validation still works.
    """
    version = latest_version()
    # The file set is read from the version being copied, not from the shared default. Since
    # 1.0.0-rc.2 the dialect is two files, and copying three would leave the wrapper's $ref
    # dangling - which is a fault in this fixture, not in the resolution being tested.
    files = meta_store.meta_files(version)
    source = meta_store.meta_dir() / version
    target = tmp_path / "meta" / "9.9.9"
    target.mkdir(parents=True)
    for name in files:
        document = json.loads((source / name).read_text(encoding="utf-8"))
        if "$id" in document:
            document["$id"] = (
                document["$id"]
                .replace("/latest/", "/9.9.9/")
                .replace("oo-ld.github.io/oold-schema", "example.invalid/elsewhere")
            )
        (target / name).write_text(json.dumps(document), encoding="utf-8")
    # Only the $id values were rewritten, so the wrapper still $refs the base at /latest/ while
    # the base now answers to /9.9.9/. That mismatch is the point: resolution is by file name.
    (tmp_path / "meta" / "index.json").write_text(
        json.dumps({"files": files, "versions": {"9.9.9": {}}, "remote": {}}), encoding="utf-8"
    )

    monkeypatch.setattr(meta_store, "meta_dir", lambda: tmp_path / "meta")
    meta_store.load_index.cache_clear()
    try:
        bundle = load_tracked("9.9.9")
        assert bundle.self_check() == []
        probe = {"$id": "https://example.org/probe.schema.json", "x-oold-ui-form-hidden": True}
        assert bundle.meta_validator().is_valid(probe)
    finally:
        meta_store.load_index.cache_clear()


def test_describe_store_reports_versions_and_cache_state(isolated_cache):
    store = describe_store()
    assert store["latest"] == latest_version()
    assert META_SCHEMA_FILE in store["files"]
    assert store["remote"]["cached"] is False


def test_remote_is_refused_offline_when_not_cached(isolated_cache):
    with pytest.raises(MetaSchemaError, match="offline"):
        resolve_selection(["remote"], offline=True)


def _remote_documents() -> dict:
    """What a fake upstream serves for ``--meta remote``: the tracked baseline, plus whatever
    ``remote.files`` in ``index.json`` adds on top (e.g. a wrapper/base split no tracked version
    has yet). A minimal, self-contained schema stands in for a file no tracked version ships.
    """
    source = meta_store.meta_dir() / latest_version()
    documents = {}
    for name in meta_store.meta_files(meta_store.REMOTE):
        path = source / name
        if path.is_file():
            documents[name] = json.loads(path.read_text("utf-8"))
        else:
            documents[name] = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": f"https://example.invalid/{name}",
            }
    return documents


class _FakeUpstream:
    """A conditional-GET origin server, near enough: one etag per file, bumped by `revision`.

    Upstream serves the meta-schemas but not (yet) the optional rule catalog; a missing file
    surfaces as a resolution error, the same as a real 404.
    """

    def __init__(self, documents):
        self.documents = documents
        self.revision = 1
        self.requests: list[tuple[str, str | None]] = []

    def etag_for(self, name):
        return f'"{name}-r{self.revision}"'

    def __call__(self, uri, etag=None, timeout=10.0):
        name = uri.rsplit("/", 1)[-1]
        self.requests.append((name, etag))
        if name not in self.documents:
            raise SchemaResolutionError(f"could not fetch {uri}: 404")
        current = self.etag_for(name)
        if etag == current:
            return None, current
        return self.documents[name], current


def test_remote_fetch_writes_only_to_the_cache(isolated_cache, monkeypatch, tmp_path):
    """A remote fetch must never touch the tracked version history."""
    documents = _remote_documents()
    before = {path: path.read_bytes() for path in meta_store.meta_dir().rglob("*.json")}

    monkeypatch.setattr(meta_store, "http_get_json_if_changed", _FakeUpstream(documents))
    bundle = meta_store.load_remote(offline=False)

    assert bundle.version == "remote"
    assert bundle.self_check() == []
    assert Path(meta_store.remote_cache_dir(), META_SCHEMA_FILE).is_file()
    after = {path: path.read_bytes() for path in meta_store.meta_dir().rglob("*.json")}
    assert after == before, "the tracked meta-schema folder was modified by a remote fetch"


def test_cached_remote_is_usable_offline(isolated_cache, monkeypatch):
    monkeypatch.setattr(meta_store, "http_get_json_if_changed", _FakeUpstream(_remote_documents()))
    meta_store.fetch_remote()
    # Now offline: the cached copy must satisfy the request without any fetch.
    monkeypatch.setattr(
        meta_store,
        "http_get_json_if_changed",
        lambda *a, **k: pytest.fail("offline mode fetched over the network"),
    )
    assert meta_store.load_remote(offline=True).version == "remote"


def test_a_cached_remote_is_revalidated_rather_than_trusted(isolated_cache, monkeypatch):
    """`remote` names a branch, so age says nothing about whether the copy still matches.

    The silent direction is the expensive one: upstream moves, the cache does not, and a run
    stays green against a disagreement that already exists.
    """
    documents = _remote_documents()
    upstream = _FakeUpstream(documents)
    monkeypatch.setattr(meta_store, "http_get_json_if_changed", upstream)
    meta_store.fetch_remote()

    # Upstream moves: same file name, new content, new etag.
    documents[META_SCHEMA_FILE] = {**documents[META_SCHEMA_FILE], "title": "moved upstream"}
    upstream.revision = 2
    upstream.requests.clear()
    meta_store.load_remote(offline=False)

    cached = json.loads(Path(meta_store.remote_cache_dir(), META_SCHEMA_FILE).read_text("utf-8"))
    assert cached["title"] == "moved upstream"
    # Revalidation is conditional, not a blind refetch: the stored etag went back out.
    sent = dict(upstream.requests)
    assert sent[META_SCHEMA_FILE] == f'"{META_SCHEMA_FILE}-r1"'


def test_an_unrevalidated_cache_says_so_in_its_origin(isolated_cache, monkeypatch):
    """An unverified copy and a confirmed one are different evidence for the same report."""
    monkeypatch.setattr(meta_store, "http_get_json_if_changed", _FakeUpstream(_remote_documents()))
    assert "not revalidated" not in meta_store.load_remote(offline=False).origin

    assert "not revalidated: offline" in meta_store.load_remote(offline=True).origin

    def unreachable(*args, **kwargs):
        raise SchemaResolutionError("could not fetch: network is down")

    monkeypatch.setattr(meta_store, "http_get_json_if_changed", unreachable)
    bundle = meta_store.load_remote(offline=False)
    assert bundle.version == "remote", "an unreachable upstream must not lose a usable cache"
    assert "not revalidated: upstream unreachable" in bundle.origin


def test_a_directory_selector_loads_the_meta_schemas_in_it(tmp_path):
    """`--meta <path>` reads a checkout, which is the only way to see an unreleased rule.

    A tracked version is a tag and `remote` is `refs/heads/main`, so a rule added on a branch is
    invisible to both: the checks bound to it skip, saying the version never stated it, and the
    pull request introducing a rule becomes the one run that cannot enforce it.
    """
    latest = meta_store.meta_dir() / meta_store.latest_version()
    checkout = tmp_path / "oold-schema" / "meta"
    checkout.mkdir(parents=True)
    for src in latest.glob("*.json"):
        (checkout / src.name).write_bytes(src.read_bytes())

    # A rule that exists only here, the way a branch would carry one.
    catalog = json.loads((checkout / meta_store.RULES_FILE).read_text(encoding="utf-8"))
    invented = dict(catalog["rules"][0], id="OOLD-XXX-beef", summary="only in the checkout")
    catalog["rules"].append(invented)
    (checkout / meta_store.RULES_FILE).write_text(json.dumps(catalog), encoding="utf-8")

    tracked = meta_store.load_tracked(meta_store.latest_version())
    # Both the repository root and its meta/ directory resolve to the same thing.
    for selector in (tmp_path / "oold-schema", checkout):
        bundle = meta_store.resolve_selection([str(selector)])[0]
        assert bundle.version == meta_store.LOCAL
        ids = {r.id for r in bundle.rules}
        assert "OOLD-XXX-beef" in ids, "a local checkout must surface a rule no release carries"
        assert ids - {"OOLD-XXX-beef"} == {r.id for r in tracked.rules}

    assert "OOLD-XXX-beef" not in {r.id for r in tracked.rules}, "the tracked copy must be untouched"


def test_a_directory_without_meta_schemas_is_rejected_by_name(tmp_path):
    """The likely mistake is pointing at the wrong directory, so say what was expected."""
    with pytest.raises(MetaSchemaError, match=meta_store.META_SCHEMA_FILE):
        meta_store.load_local(tmp_path)
