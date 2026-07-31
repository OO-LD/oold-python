"""The OO-LD meta-schema store: version history, remote fetch, and validator construction.

The meta-schemas are owned by `oold-schema <https://github.com/OO-LD/oold-schema>`_. This
package keeps a hand-curated copy of each released version under ``meta/<version>/`` (see
``meta/README.md``) so validation works offline, and so one schema can be checked against
several meta-schema versions in a single run.

Selection is by name:

==========  ===============================================================
``latest``  the highest version in the tracked folder (the default)
``0.7.0``   that tracked version
``remote``  the unreleased ``main`` state, fetched into the user cache
``all``     every tracked version
==========  ===============================================================

Remote fetches land in the user cache and never touch the tracked folder, so ``--meta remote``
cannot silently change what a released version means.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from .formats import OOLD_FORMAT_CHECKER
from .resolve import SchemaResolutionError, default_cache_dir, http_get_json

META_SCHEMA_FILE = "oold-meta-schema.json"
UI_META_SCHEMA_FILE = "oold-ui-meta-schema.json"
PATTERN_LINT_FILE = "oold-pattern-lint.schema.json"

#: The rule catalog, generated upstream from the specification prose. Unlike the three
#: meta-schemas this file is **optional**: it was introduced after 0.8.0, so a version predating
#: it must still load, simply reporting no rule ids. Findings then carry no citation rather than
#: the run failing, which is what lets an older meta version stay usable.
RULES_FILE = "oold-rules.json"

#: Selector for the unreleased upstream state.
REMOTE = "remote"
LATEST = "latest"
ALL = "all"


class MetaSchemaError(Exception):
    """A meta-schema version could not be loaded."""


def meta_dir() -> Path:
    """The tracked version-history folder that ships inside the package."""
    return Path(__file__).parent / "meta"


def remote_cache_dir() -> Path:
    """Where fetched (unreleased) meta-schemas are cached. Never the tracked folder."""
    return default_cache_dir() / "meta" / "remote-main"


@lru_cache(maxsize=1)
def load_index() -> dict[str, Any]:
    """Read ``meta/index.json``, which records provenance for each tracked version."""
    path = meta_dir() / "index.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MetaSchemaError(f"meta-schema index missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MetaSchemaError(f"meta-schema index is not valid JSON: {exc}") from exc


def meta_files() -> list[str]:
    index = load_index()
    files = index.get("files")
    if not isinstance(files, list) or not files:
        return [META_SCHEMA_FILE, PATTERN_LINT_FILE, UI_META_SCHEMA_FILE]
    return list(files)


def remote_base_url() -> str:
    remote = load_index().get("remote") or {}
    base = remote.get("base_url")
    if not base:
        raise MetaSchemaError("meta/index.json declares no remote.base_url")
    return str(base)


def _version_key(version: str) -> tuple:
    """Sort key that orders 0.10.0 after 0.9.0 rather than before it."""
    parts: list[Any] = []
    for chunk in version.split("."):
        parts.append((0, int(chunk)) if chunk.isdigit() else (1, chunk))
    return tuple(parts)


def tracked_versions() -> list[str]:
    """Every version present in the tracked folder, oldest first."""
    root = meta_dir()
    if not root.is_dir():
        return []
    found = [entry.name for entry in root.iterdir() if entry.is_dir() and (entry / META_SCHEMA_FILE).is_file()]
    return sorted(found, key=_version_key)


def latest_version() -> str:
    versions = tracked_versions()
    if not versions:
        raise MetaSchemaError(f"no meta-schema versions are tracked in {meta_dir()}; see its README.md")
    return versions[-1]


# ---------------------------------------------------------------------------- bundle


@dataclass
class MetaBundle:
    """The meta-schemas for one version, plus the registry that resolves between them."""

    version: str
    origin: str
    documents: dict[str, Any]
    registry: Registry = field(repr=False)
    #: The rule catalog for this version, empty when it predates one.
    rules: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def meta(self) -> dict[str, Any]:
        return self.documents[META_SCHEMA_FILE]

    @property
    def has_rules(self) -> bool:
        return bool(self.rules)

    def rule(self, rule_id: str) -> dict[str, Any] | None:
        """Look up one rule, or None when this version ships no catalog or lacks the id."""
        return next((r for r in self.rules if r["id"] == rule_id), None)

    def checkable_rules(self) -> list[dict[str, Any]]:
        """Rules a validator can enforce by inspecting a document.

        `implementation` rules constrain a library rather than a document, and `advisory` ones
        constrain nobody, so neither belongs in a validator's coverage figure.
        """
        return [
            r
            for r in self.rules
            if r.get("checkable") and r.get("applies_to") == "document" and not r.get("deprecated")
        ]

    @property
    def ui_meta(self) -> dict[str, Any]:
        return self.documents[UI_META_SCHEMA_FILE]

    @property
    def pattern_lint(self) -> dict[str, Any]:
        return self.documents[PATTERN_LINT_FILE]

    def validator(self, document: dict[str, Any]) -> Draft202012Validator:
        """A validator for one of this bundle's schemas, with formats asserted."""
        return Draft202012Validator(document, registry=self.registry, format_checker=OOLD_FORMAT_CHECKER)

    def meta_validator(self) -> Draft202012Validator:
        return self.validator(self.meta)

    def pattern_lint_validator(self) -> Draft202012Validator:
        return self.validator(self.pattern_lint)

    def self_check(self) -> list[str]:
        """Problems with the meta-schemas themselves, as data rather than exceptions.

        The reference harness gets this for free when ajv compiles the meta-schema
        (``validate.mjs`` line 68). Here it is explicit, so a badly curated version folder is
        reported as a failing check rather than crashing mid-run.
        """
        problems: list[str] = []
        for name, document in sorted(self.documents.items()):
            try:
                Draft202012Validator.check_schema(document)
            except SchemaError as exc:
                problems.append(f"{name} is not a valid JSON Schema 2020-12 document: {exc.message}")
        return problems

    def declared_keywords(self) -> list[str]:
        """Every ``x-oold-*`` / ``x-oold-ui-*`` keyword the meta-schemas define.

        Used by the vocabulary-coverage cross-check, which fails when a keyword exists in the
        meta-schemas but no compliance fixture exercises it.
        """
        keywords = [key for key in (self.meta.get("properties") or {}) if key.startswith("x-oold-")]
        ui_keywords = (self.ui_meta.get("$defs") or {}).get("keywords", {}).get("properties") or {}
        keywords.extend(ui_keywords)
        return sorted(set(keywords))


def _build_registry(documents: dict[str, Any]) -> Registry:
    """Register each document under its ``$id``, and resolve anything else by file name.

    The file-name fallback is load-bearing rather than defensive. The canonical ``$id`` domain
    has already moved once (``oo-ld.github.io/oold-schema`` before 0.7.0, ``oo-ld.org`` after),
    and a released copy stamps its version in place of ``latest`` while its internal ``$ref``
    may still say ``latest``. Matching on the file name makes the bundle self-consistent
    whatever URL scheme a given release happens to use. JSON Schema 2020-12 itself is not
    handled here; it comes from the specifications bundled with ``referencing``.
    """
    resources = {
        name: Resource.from_contents(document, default_specification=DRAFT202012)
        for name, document in documents.items()
    }

    def retrieve(uri: str) -> Resource:
        basename = uri.split("#", 1)[0].rsplit("/", 1)[-1]
        if basename in resources:
            return resources[basename]
        raise MetaSchemaError(f"the meta-schema bundle references {uri!r}, which is not one of its files")

    pairs = []
    for name, document in documents.items():
        declared = document.get("$id")
        pairs.append((str(declared) if declared else name, resources[name]))
    return Registry(retrieve=retrieve).with_resources(pairs)


def _read_rules(directory: Path) -> list[dict[str, Any]]:
    """Load the optional rule catalog from a version directory.

    A malformed catalog is treated as absent rather than fatal: rule ids are an annotation on
    findings, so losing them must never stop a schema from being validated.
    """
    path = directory / RULES_FILE
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("rules", [])
    except (OSError, json.JSONDecodeError):
        return []


def _read_documents(directory: Path, label: str) -> dict[str, Any]:
    documents: dict[str, Any] = {}
    for name in meta_files():
        path = directory / name
        try:
            documents[name] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MetaSchemaError(f"{label} is missing {name} (looked in {directory})") from exc
        except json.JSONDecodeError as exc:
            raise MetaSchemaError(f"{label}: {name} is not valid JSON: {exc}") from exc
    return documents


def load_tracked(version: str) -> MetaBundle:
    """Load one tracked version from the package."""
    directory = meta_dir() / version
    if not directory.is_dir():
        available = ", ".join(tracked_versions()) or "none"
        raise MetaSchemaError(f"meta-schema version {version!r} is not tracked (available: {available})")
    documents = _read_documents(directory, f"meta-schema version {version}")
    return MetaBundle(
        version=version,
        origin=str(directory),
        documents=documents,
        registry=_build_registry(documents),
        rules=_read_rules(directory),
    )


# ---------------------------------------------------------------------------- remote


def fetch_remote(force: bool = False, timeout: float = 10.0) -> Path:
    """Fetch the unreleased ``main`` meta-schemas into the user cache and return its path."""
    target = remote_cache_dir()
    stamp = target / "fetched.json"
    if not force and all((target / name).is_file() for name in meta_files()):
        return target

    base = remote_base_url()
    target.mkdir(parents=True, exist_ok=True)
    for name in meta_files():
        document = http_get_json(base + name, timeout=timeout)
        (target / name).write_text(json.dumps(document, indent=2), encoding="utf-8")
    try:
        catalog = http_get_json(base + RULES_FILE, timeout=timeout)
        (target / RULES_FILE).write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    except SchemaResolutionError:
        # Upstream has not published a catalog yet; the bundle is still complete without it.
        (target / RULES_FILE).unlink(missing_ok=True)
    stamp.write_text(
        json.dumps(
            {
                "base_url": base,
                "fetched": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "files": meta_files(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def load_remote(offline: bool = False, timeout: float = 10.0) -> MetaBundle:
    """Load the ``main`` meta-schemas, from the cache when offline."""
    target = remote_cache_dir()
    cached = all((target / name).is_file() for name in meta_files())

    if not cached:
        if offline:
            raise MetaSchemaError(
                "refusing network fetch (offline): the remote meta-schemas are not cached. "
                "Run `oold meta fetch` once while online, or select a tracked version."
            )
        try:
            target = fetch_remote(timeout=timeout)
        except SchemaResolutionError as exc:
            raise MetaSchemaError(f"could not fetch the remote meta-schemas: {exc}") from exc

    documents = _read_documents(target, "the remote meta-schemas")
    origin = str(target)
    stamp = target / "fetched.json"
    if stamp.is_file():
        # The stamp is provenance for the report, so a corrupt one must not fail the run.
        with contextlib.suppress(OSError, json.JSONDecodeError, KeyError):
            origin = f"{target} (fetched {json.loads(stamp.read_text(encoding='utf-8'))['fetched']})"
    return MetaBundle(
        version=REMOTE,
        origin=origin,
        documents=documents,
        registry=_build_registry(documents),
        rules=_read_rules(target),
    )


# ---------------------------------------------------------------------------- selection


def resolve_selection(
    selectors: str | list[str] | tuple[str, ...] = (LATEST,),
    offline: bool = False,
    timeout: float = 10.0,
) -> list[MetaBundle]:
    """Turn ``--meta`` selectors into bundles, in the order given and without duplicates."""
    if isinstance(selectors, str):
        selectors = [selectors]
    requested = list(selectors) or [LATEST]

    wanted: list[str] = []
    for selector in requested:
        name = selector.strip()
        if name == ALL:
            resolved = tracked_versions()
            if not resolved:
                raise MetaSchemaError(f"no meta-schema versions are tracked in {meta_dir()}")
        elif name == LATEST:
            resolved = [latest_version()]
        else:
            resolved = [name]
        for version in resolved:
            if version not in wanted:
                wanted.append(version)

    bundles: list[MetaBundle] = []
    for version in wanted:
        if version == REMOTE:
            bundles.append(load_remote(offline=offline, timeout=timeout))
        else:
            bundles.append(load_tracked(version))
    return bundles


def describe_store() -> dict[str, Any]:
    """What ``oold meta list`` prints: tracked versions, provenance and cache state."""
    index = load_index()
    versions = tracked_versions()
    cache = remote_cache_dir()
    cached = all((cache / name).is_file() for name in meta_files())

    fetched = None
    stamp = cache / "fetched.json"
    if stamp.is_file():
        try:
            fetched = json.loads(stamp.read_text(encoding="utf-8")).get("fetched")
        except (OSError, json.JSONDecodeError):
            fetched = None

    return {
        "tracked_dir": str(meta_dir()),
        "versions": [{"version": v, **(index.get("versions", {}).get(v) or {})} for v in versions],
        "latest": versions[-1] if versions else None,
        "files": meta_files(),
        "remote": {
            "base_url": (index.get("remote") or {}).get("base_url"),
            "cache_dir": str(cache),
            "cached": cached,
            "fetched": fetched,
        },
    }
