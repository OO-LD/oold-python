"""`oold meta vendor`: the command that writes the tracked meta-schema store.

Everything else in this package only reads ``meta/``; this is the one path that writes it, so
these tests build a small real git repository per test rather than faking git's behaviour, since
the property under test - byte-exact extraction, immune to the working tree's line endings - is
about what git plumbing actually returns.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from oold.validation import meta_store, meta_vendor
from oold.validation.meta_store import MetaSchemaError

# The three files every version predating the 1.0.0-rc.2 split ships - the shared default.
_CORE_DOCUMENTS = (meta_store.META_SCHEMA_FILE, meta_store.PATTERN_LINT_FILE, meta_store.UI_META_SCHEMA_FILE)


def _run_git(cwd: Path, *args: str) -> None:
    # S603/S607: a fixed executable ("git") with literal, test-authored arguments, never
    # untrusted input.
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)  # noqa: S603, S607


def _git_output(cwd: Path, *args: str) -> str:
    """Run a git command and return its stdout, stripped - for assertions, not fixture setup."""
    # S603/S607: see _run_git above.
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)  # noqa: S603, S607
    return result.stdout.strip()


def _commit_and_tag(repo: Path, version: str) -> None:
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", f"release {version}")
    _run_git(repo, "tag", f"v{version}")


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    """A minimal git-initialised checkout, standing in for an oold-schema clone."""
    repo = tmp_path / "source"
    (repo / "meta").mkdir(parents=True)
    (repo / "examples" / "compliance").mkdir(parents=True)
    _run_git(repo, "init", "-q")
    _run_git(repo, "config", "user.email", "test@example.com")
    _run_git(repo, "config", "user.name", "Test")
    # The point of this suite is what git plumbing returns, not what a Windows default would do
    # to it on the way in; each test controls line endings explicitly instead.
    _run_git(repo, "config", "core.autocrlf", "false")
    return repo


@pytest.fixture
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An isolated tracked folder and fixture destination, so a test never touches the real ones."""
    meta_root = tmp_path / "tracked-meta"
    meta_root.mkdir()
    index = {
        "files": list(_CORE_DOCUMENTS),
        "versions": {},
        "fixtures": {"tag": "v0.0.0"},
    }
    (meta_root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    monkeypatch.setattr(meta_store, "meta_dir", lambda: meta_root)
    meta_store.load_index.cache_clear()

    fixtures_root = tmp_path / "fixtures"
    (fixtures_root / "compliance").mkdir(parents=True)
    monkeypatch.setattr(meta_vendor, "_fixtures_dir", lambda: fixtures_root)

    try:
        yield meta_root, fixtures_root
    finally:
        meta_store.load_index.cache_clear()


def _write_core_documents(repo: Path, *, id_base: str = "https://example.org/1.2.3/meta/") -> None:
    for name in _CORE_DOCUMENTS:
        (repo / "meta" / name).write_text(json.dumps({"$id": id_base + name}), encoding="utf-8")


def test_vendor_writes_the_shipped_files_with_matching_checksums(source_repo, isolated_store):
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    result = meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    assert set(result.files) == set(_CORE_DOCUMENTS)
    index = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))
    recorded = index["versions"]["1.2.3"]["sha256"]
    for name in _CORE_DOCUMENTS:
        content = (meta_root / "1.2.3" / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == recorded[name]


def test_the_written_index_json_has_no_crlf(source_repo, isolated_store):
    """`Path.write_text`'s default `newline` translates "\\n" to `os.linesep`, which on Windows
    is CRLF - the same trap the vendored files avoid by being written with `write_bytes`, just
    reappearing in the one file this command writes as text. Asserted on the bytes, the way
    `test_the_vendored_files_are_stored_with_unix_line_endings` checks the vendored files, since
    that is the form of the check that actually travels across platforms.
    """
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    assert b"\r\n" not in (meta_root / "index.json").read_bytes()


def test_vendor_records_tag_commit_and_commit_date(source_repo, isolated_store):
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")

    result = meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    commit = _git_output(source_repo, "rev-parse", "v1.2.3^{commit}")
    committed = _git_output(source_repo, "log", "-1", "--format=%cI", commit)
    assert result.tag == "v1.2.3"
    assert result.commit == commit
    assert len(result.commit) == 40
    assert result.committed == committed


def test_vendor_omits_files_override_when_the_set_matches_the_default(source_repo, isolated_store):
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    entry = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))["versions"]["1.2.3"]
    assert "files" not in entry


def test_vendor_records_a_files_override_when_the_base_is_present(source_repo, isolated_store):
    _write_core_documents(source_repo)
    (source_repo / "meta" / meta_store.META_SCHEMA_BASE_FILE).write_text(
        json.dumps({"$id": "https://example.org/1.2.3/meta/" + meta_store.META_SCHEMA_BASE_FILE}),
        encoding="utf-8",
    )
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    entry = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))["versions"]["1.2.3"]
    assert entry["files"] == [
        meta_store.META_SCHEMA_FILE,
        meta_store.META_SCHEMA_BASE_FILE,
        meta_store.PATTERN_LINT_FILE,
        meta_store.UI_META_SCHEMA_FILE,
    ]


def test_vendor_includes_the_optional_rule_files_without_a_files_override(source_repo, isolated_store):
    _write_core_documents(source_repo)
    (source_repo / "meta" / meta_store.RULES_FILE).write_text(json.dumps({"rules": []}), encoding="utf-8")
    (source_repo / "meta" / meta_store.RULES_SCHEMA_FILE).write_text(json.dumps({"type": "object"}), encoding="utf-8")
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    result = meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    entry = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))["versions"]["1.2.3"]
    assert "files" not in entry, "the rule catalogue is not part of the registry's document set"
    assert meta_store.RULES_FILE in entry["sha256"]
    assert meta_store.RULES_SCHEMA_FILE in entry["sha256"]
    assert meta_store.RULES_FILE in result.files
    assert (meta_root / "1.2.3" / meta_store.RULES_FILE).is_file()


def test_vendor_ignores_files_under_meta_that_are_not_part_of_the_bundle(source_repo, isolated_store):
    """oold-schema's meta/ also carries RULES.md and rules-baseline.json - authoring tooling, not
    part of what any tracked version loads. Copying them would be exactly the "wrong file set"
    mistake this command exists to remove.
    """
    _write_core_documents(source_repo)
    (source_repo / "meta" / "RULES.md").write_text("not a schema", encoding="utf-8")
    (source_repo / "meta" / "rules-baseline.json").write_text("{}", encoding="utf-8")
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    result = meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    assert "RULES.md" not in result.files
    assert "rules-baseline.json" not in result.files
    assert not (meta_root / "1.2.3" / "RULES.md").exists()
    assert not (meta_root / "1.2.3" / "rules-baseline.json").exists()


def test_vendor_records_id_base_from_the_wrapper_document(source_repo, isolated_store):
    _write_core_documents(source_repo, id_base="https://oo-ld.org/1.2.3/meta/")
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, _ = isolated_store

    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    entry = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))["versions"]["1.2.3"]
    assert entry["id_base"] == "https://oo-ld.org/1.2.3/meta/"


def test_vendored_files_are_written_with_lf_even_when_the_working_tree_has_crlf(source_repo, isolated_store):
    """The CRLF trap: a checkout's working tree can hold CRLF - from `core.autocrlf=true` on
    Windows, or, as here, from something dirtying the file after the commit - while the committed
    blob stays LF. The command must read the blob, never the working tree file, so the two can
    disagree and the output still matches the blob.
    """
    _write_core_documents(source_repo)
    committed_bytes = (source_repo / "meta" / meta_store.META_SCHEMA_FILE).read_bytes()
    assert b"\r\n" not in committed_bytes
    _commit_and_tag(source_repo, "1.2.3")

    # Dirty the working tree after the commit: same content, CRLF line endings. The blob in the
    # object database is untouched.
    (source_repo / "meta" / meta_store.META_SCHEMA_FILE).write_bytes(committed_bytes.replace(b"\n", b"\r\n"))

    meta_root, _ = isolated_store
    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    written = (meta_root / "1.2.3" / meta_store.META_SCHEMA_FILE).read_bytes()
    assert b"\r\n" not in written
    assert written == committed_bytes
    entry = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))["versions"]["1.2.3"]
    assert entry["sha256"][meta_store.META_SCHEMA_FILE] == hashlib.sha256(committed_bytes).hexdigest()


def test_vendor_refuses_to_overwrite_an_existing_version_without_force(source_repo, isolated_store):
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")
    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    with pytest.raises(MetaSchemaError, match="--force"):
        meta_vendor.vendor_version("1.2.3", source_repo, force=False)


def test_vendor_with_force_overwrites_an_existing_version(source_repo, isolated_store):
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")
    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    (source_repo / "meta" / meta_store.META_SCHEMA_FILE).write_text(
        json.dumps({"$id": "https://example.org/1.2.3/meta/" + meta_store.META_SCHEMA_FILE, "changed": True}),
        encoding="utf-8",
    )
    _run_git(source_repo, "add", "-A")
    _run_git(source_repo, "commit", "-q", "-m", "amend release 1.2.3")
    _run_git(source_repo, "tag", "-f", "v1.2.3")

    result = meta_vendor.vendor_version("1.2.3", source_repo, force=True)
    meta_root, _ = isolated_store
    written = json.loads((meta_root / "1.2.3" / meta_store.META_SCHEMA_FILE).read_text(encoding="utf-8"))
    assert written["changed"] is True
    assert result.commit


def test_vendor_reports_a_missing_tag_clearly(source_repo, isolated_store):
    _write_core_documents(source_repo)
    _commit_and_tag(source_repo, "1.2.3")

    with pytest.raises(MetaSchemaError, match=re.escape("9.9.9")):
        meta_vendor.vendor_version("9.9.9", source_repo, force=False)


def test_vendor_refuses_a_tag_with_no_meta_schema_wrapper(source_repo, isolated_store):
    (source_repo / "meta" / meta_store.PATTERN_LINT_FILE).write_text(
        json.dumps({"$id": "https://example.org/1.2.3/meta/" + meta_store.PATTERN_LINT_FILE}), encoding="utf-8"
    )
    _commit_and_tag(source_repo, "1.2.3")

    with pytest.raises(MetaSchemaError, match=meta_store.META_SCHEMA_FILE):
        meta_vendor.vendor_version("1.2.3", source_repo, force=False)


def test_vendor_refreshes_the_fixture_slice_and_records_its_tag(source_repo, isolated_store):
    _write_core_documents(source_repo)
    (source_repo / "examples" / "Thing.schema.json").write_text(json.dumps({"name": "Thing"}), encoding="utf-8")
    (source_repo / "examples" / "compliance" / "rule.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    _commit_and_tag(source_repo, "1.2.3")
    meta_root, fixtures_root = isolated_store

    result = meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    assert (fixtures_root / "Thing.schema.json").read_text(encoding="utf-8") == json.dumps({"name": "Thing"})
    assert (fixtures_root / "compliance" / "rule.json").read_text(encoding="utf-8") == json.dumps({"ok": True})
    assert "Thing.schema.json" in result.fixture_files
    assert "compliance/rule.json" in result.fixture_files
    index = json.loads((meta_root / "index.json").read_text(encoding="utf-8"))
    assert index["fixtures"]["tag"] == "v1.2.3"


def test_fixture_refresh_never_touches_locally_authored_directories(source_repo, isolated_store):
    """`broken/`, `remote_context/` and `x_oold_context/` are hand-written and not part of any
    upstream tag; the refresh must never see them, since it only ever descends into `examples/`
    and `examples/compliance/` on the source side.
    """
    _write_core_documents(source_repo)
    (source_repo / "examples" / "Thing.schema.json").write_text(json.dumps({"name": "Thing"}), encoding="utf-8")
    _commit_and_tag(source_repo, "1.2.3")
    _, fixtures_root = isolated_store
    broken_dir = fixtures_root / "broken"
    broken_dir.mkdir()
    (broken_dir / "invalid_meta.schema.json").write_text("{}", encoding="utf-8")
    before = (broken_dir / "invalid_meta.schema.json").read_bytes()

    meta_vendor.vendor_version("1.2.3", source_repo, force=False)

    assert (broken_dir / "invalid_meta.schema.json").read_bytes() == before
