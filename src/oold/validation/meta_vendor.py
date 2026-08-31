"""Vendor a released meta-schema version from an oold-schema checkout.

``meta_store.py`` only ever reads the tracked tree; this module is the one place that writes it,
and only in response to an explicit ``oold meta vendor`` invocation - never at validation time.

It exists to remove, by construction, three mistakes the hand-run procedure in
``docs/maintaining-meta-schemas.md`` could only warn about:

- ``git show`` instead of ``git cat-file blob``, which applies the checkout's autocrlf filter and
  writes CRLF on Windows, changing every recorded digest and failing only once it reaches Linux
  CI. Every file below is read with ``git cat-file blob`` and written with :meth:`Path.write_bytes`,
  so nothing in the path ever re-encodes a line ending.
- copying the wrong file set. The set has grown twice already (the rule catalogue in 1.0.0-rc.1,
  the meta-schema base in 1.0.0-rc.2), so this reads what the tag's ``meta/`` directory actually
  contains rather than a fixed list a human has to remember to edit.
- updating the vendored files but not ``fixtures.tag``. The two writes happen in one call, from
  one resolved tag, so they cannot drift apart the way a two-step manual procedure did.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import meta_store

#: Meta-schema documents, in the order they get committed with. Not every version ships every one
#: - the base split off in 1.0.0-rc.2 - so which of these a version records is decided by what its
#: tag actually contains, never assumed.
_CANDIDATE_DOCUMENTS = (
    meta_store.META_SCHEMA_FILE,
    meta_store.META_SCHEMA_BASE_FILE,
    meta_store.PATTERN_LINT_FILE,
    meta_store.UI_META_SCHEMA_FILE,
)

#: The rule catalogue and its schema, optional and never part of a version's ``files`` override:
#: unlike the documents above they are not loaded through the registry, so meta_files() has no
#: reason to know about them.
_CANDIDATE_RULE_FILES = (meta_store.RULES_FILE, meta_store.RULES_SCHEMA_FILE)


@dataclass
class VendorResult:
    """What one ``vendor_version`` call did, for the CLI to report."""

    version: str
    tag: str
    commit: str
    committed: str
    files: list[str]
    fixture_files: list[str]


def _fixtures_dir() -> Path:
    """``tests/data/oold/`` in this checkout, located from this file rather than the CWD.

    A separate lookup from :func:`meta_store.meta_dir`, because this directory ships only in a
    source checkout, never in the installed package - the same reason the fixture refresh half of
    this module is a repository-maintenance operation rather than something ``oold`` needs at
    runtime.
    """
    # src/oold/validation/meta_vendor.py -> repository root is three parents up.
    return Path(__file__).resolve().parents[3] / "tests" / "data" / "oold"


def _git(source: Path, *args: str) -> str:
    """Run a git command in ``source`` and return its stdout as text, stripped."""
    # S603/S607: "git" is not resolved from an untrusted PATH here - it is the same interpreter
    # this whole toolchain already depends on, and args are fixed revision/path literals, never
    # user-supplied shell text.
    result = subprocess.run(["git", "-C", str(source), *args], capture_output=True)  # noqa: S603, S607
    if result.returncode != 0:
        raise meta_store.MetaSchemaError(
            f"git {' '.join(args)} failed in {source}: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout.decode(errors="replace").strip()


def _git_blob(source: Path, rev: str) -> bytes:
    """The verbatim bytes of one blob, bypassing any working-tree line-ending conversion.

    ``git cat-file blob``, never ``git show``: ``show`` applies the checkout's autocrlf filter,
    which on Windows turns LF into CRLF and changes every digest computed from the result. The
    bytes are captured directly from the subprocess pipe and written with :meth:`Path.write_bytes`
    - no text-mode decoding happens anywhere between the object database and the file on disk.
    """
    # S603/S607: see _git above.
    result = subprocess.run(["git", "-C", str(source), "cat-file", "blob", rev], capture_output=True)  # noqa: S603, S607
    if result.returncode != 0:
        raise meta_store.MetaSchemaError(
            f"git cat-file blob {rev} failed in {source}: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def _ls_tree(source: Path, rev: str, directory: str) -> list[str]:
    """File names (not full paths) one level under ``directory`` at ``rev``."""
    listing = _git(source, "ls-tree", "--name-only", rev, directory)
    return [Path(line).name for line in listing.splitlines() if line]


def _id_base(document: dict[str, Any], filename: str) -> str:
    """The ``$id`` base this release publishes under, derived from its own wrapper document.

    Recorded per version rather than assumed, because the canonical domain has already moved once
    (see :func:`meta_store._build_registry`); reading it from the file itself means a future move
    needs only a new vendored entry, never a code change here.
    """
    declared = document.get("$id")
    if not isinstance(declared, str) or not declared.endswith(filename):
        raise meta_store.MetaSchemaError(f"{filename}'s $id does not end with its own file name: {declared!r}")
    return declared[: -len(filename)]


def _refresh_fixtures(source: Path, tag: str) -> list[str]:
    """Copy the fixture slice from ``examples/`` at ``tag``, mirroring the documented procedure.

    Only the top level and ``compliance/`` are upstream; ``broken/``, ``remote_context/`` and
    ``x_oold_context/`` are written here by hand and this never touches them, because it never
    looks anywhere but those two source directories.
    """
    dest = _fixtures_dir()
    written: list[str] = []

    for name in _ls_tree(source, tag, "examples/"):
        if not name.endswith(".json"):
            continue
        (dest / name).write_bytes(_git_blob(source, f"{tag}:examples/{name}"))
        written.append(name)

    dest_compliance = dest / "compliance"
    for name in _ls_tree(source, tag, "examples/compliance/"):
        (dest_compliance / name).write_bytes(_git_blob(source, f"{tag}:examples/compliance/{name}"))
        written.append(f"compliance/{name}")

    return written


def vendor_version(version: str, source: Path, *, force: bool = False) -> VendorResult:
    """Vendor one released meta-schema version from ``source``, and refresh the fixture slice.

    ``source`` is a checkout of oold-schema; ``version`` names the release, whose tag is assumed
    to be ``v<version>`` - the convention every tracked entry in ``index.json`` already follows.
    Refuses to overwrite a version already present in the tracked folder or the index unless
    ``force`` is set, so a typo'd version cannot silently discard a curated entry.
    """
    index = meta_store.load_index()
    target_dir = meta_store.meta_dir() / version
    already_tracked = version in index.get("versions", {}) or target_dir.is_dir()
    if already_tracked and not force:
        raise meta_store.MetaSchemaError(
            f"meta-schema version {version!r} is already tracked; pass --force to overwrite it"
        )

    tag = f"v{version}"
    commit = _git(source, "rev-parse", f"{tag}^{{commit}}")
    committed = _git(source, "log", "-1", "--format=%cI", commit)

    present = set(_ls_tree(source, tag, "meta/"))
    documents = [name for name in _CANDIDATE_DOCUMENTS if name in present]
    if meta_store.META_SCHEMA_FILE not in documents:
        raise meta_store.MetaSchemaError(f"{tag} carries no {meta_store.META_SCHEMA_FILE} under meta/ in {source}")
    rule_files = [name for name in _CANDIDATE_RULE_FILES if name in present]
    all_files = documents + rule_files

    target_dir.mkdir(parents=True, exist_ok=True)
    sha256: dict[str, str] = {}
    for name in all_files:
        content = _git_blob(source, f"{tag}:meta/{name}")
        (target_dir / name).write_bytes(content)
        sha256[name] = hashlib.sha256(content).hexdigest()

    wrapper = json.loads((target_dir / meta_store.META_SCHEMA_FILE).read_bytes())
    id_base = _id_base(wrapper, meta_store.META_SCHEMA_FILE)

    entry: dict[str, Any] = {
        "tag": tag,
        "commit": commit,
        "committed": committed,
        "added": datetime.now(timezone.utc).date().isoformat(),
        "id_base": id_base,
        "sha256": sha256,
    }
    # Mirrors the fallback in meta_store.meta_files(): the three files every version predating the
    # 1.0.0-rc.2 split ships, and the default this version's own set is compared against below.
    default_documents = index.get("files") or [
        meta_store.META_SCHEMA_FILE,
        meta_store.PATTERN_LINT_FILE,
        meta_store.UI_META_SCHEMA_FILE,
    ]
    if documents != default_documents:
        entry["files"] = documents

    index.setdefault("versions", {})[version] = entry

    fixture_files = _refresh_fixtures(source, tag)
    index.setdefault("fixtures", {})["tag"] = tag

    index_path = meta_store.meta_dir() / "index.json"
    # newline="\n": write_text defaults to translating "\n" to os.linesep, which on Windows would
    # author this file with CRLF - the same trap the vendored files avoid by being written with
    # write_bytes, just reappearing in the one file this command writes as text.
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    meta_store.load_index.cache_clear()

    return VendorResult(
        version=version,
        tag=tag,
        commit=commit,
        committed=committed,
        files=all_files,
        fixture_files=fixture_files,
    )
