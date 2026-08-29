"""Document loading, ``$ref`` dereferencing and schema bounding.

A schema can be given as a dict, a :class:`~pathlib.Path`, a file path string, a raw JSON
string, or a URL. Everything normalises to a :class:`ResolvedSchema`, whose ``base_uri`` is what
relative ``$ref`` and relative ``@context`` entries resolve against. Local files get a
``file://`` base URI so one code path covers local and remote alike.

Remote documents are cached on disk, so a repeated run does not refetch them. ``offline=True``
restricts resolution to local files and the warm cache, with the network refused.

:func:`dereference` deliberately produces a *graph*, with shared and circular references, the
way ``json-schema-ref-parser`` does. :func:`bound_schema` then turns that graph back into a
finite tree. Keeping the two separate is what lets the bounding pass see the real sharing
structure and cut it consistently.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

#: Matches the `/C:` a Windows drive letter gets in a file URI path.
_DRIVE_PREFIX = re.compile(r"^/[A-Za-z]:")

#: Cut marker substituted for a cycle or an over-deep node.
#:
#: It must stay permissive for validation: a *typed* cut would reject legitimate values at a node
#: that is shared with an intact path. Carrying only a custom ``format`` gives two properties at
#: once. Validation has no assertion for an unknown format and the node declares no ``type``, so
#: it accepts anything; and the generator treats a ``format`` node as a string, emitting a
#: deterministic marker. The second half matters because at a *typeless* node the generator would
#: otherwise be free to emit a boolean or a number, and a non-string under an ``@type: "@id"``
#: term becomes an RDF literal that cannot compact back, which reads as a false round-trip loss.
CUT_FORMAT = "x-oold-cut"
CUT_SCHEMA: dict[str, Any] = {"format": CUT_FORMAT}

#: Instance-nesting depth budget for :func:`bound_schema`.
DEFAULT_MAX_DEPTH = 6

#: Keywords whose value describes a nested instance level; descending costs depth budget.
INSTANCE_KEYWORDS = frozenset({
    "items",
    "additionalItems",
    "additionalProperties",
    "contains",
    "propertyNames",
    "unevaluatedItems",
    "unevaluatedProperties",
})
#: Keywords whose *members'* values describe a nested instance level.
INSTANCE_MAP_KEYWORDS = frozenset({"properties", "patternProperties"})

#: Dropped from every node while bounding. Dereferencing inlines a ``$ref``'d leaf under many
#: properties, each keeping its ``$id``, which would make one ``$id`` resolve to several schemas.
IDENTITY_KEYWORDS = frozenset({"$id", "$schema"})


def default_cache_dir() -> Path:
    override = os.environ.get("OOLD_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "oold"


class SchemaResolutionError(Exception):
    """A schema or one of its references could not be loaded."""


@dataclass
class ResolvedSchema:
    """A loaded schema plus the base URI its relative references resolve against."""

    schema: dict[str, Any]
    base_uri: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.schema, dict):
            raise SchemaResolutionError(f"expected a JSON object at the schema root, got {type(self.schema).__name__}")


@dataclass
class DereferenceResult:
    """A dereferenced schema plus what could not be resolved along the way."""

    schema: Any
    unresolved: list[str] = field(default_factory=list)
    resolved_refs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unresolved


def is_url(text: str) -> bool:
    return urlsplit(text).scheme in {"http", "https", "file"}


def uri_to_path(uri: str) -> Path | None:
    """Convert a ``file://`` URI back to a local path, or None for other schemes.

    ``Path.from_uri`` arrived in Python 3.13 and handles Windows drive letters and UNC paths
    properly. Older versions fall back to ``url2pathname``, whose Windows implementation lives
    in ``nturl2path`` and is deprecated from 3.14 - which is exactly the range where the
    fallback no longer runs.
    """
    parts = urlsplit(uri)
    if parts.scheme != "file":
        return None

    from_uri = getattr(Path, "from_uri", None)
    if from_uri is not None:  # Python 3.13+
        try:
            return from_uri(uri)
        except ValueError:
            return None

    # Fallback for 3.10-3.12. Every file URI this package handles was produced by
    # `Path.as_uri()`, so the shapes are known: an optional UNC authority, and on Windows a
    # leading slash before the drive letter.
    path = unquote(parts.path)
    if parts.netloc:
        return Path(f"//{parts.netloc}{path}")
    if os.name == "nt" and _DRIVE_PREFIX.match(path):
        path = path[1:]
    return Path(path)


class Resolver:
    """Loads documents and resolves references, with a memory and on-disk cache.

    One instance is meant to be reused for a whole run, and across MCP tool calls in one
    session, so a document referenced many times is fetched once.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        timeout: float = 10.0,
        offline: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else default_cache_dir() / "documents"
        self.timeout = timeout
        self.offline = offline
        self._memory: dict[str, Any] = {}
        #: URIs fetched over the network in this session, for reporting and tests.
        self.fetched: list[str] = []

    # ------------------------------------------------------------------ loading

    def load(self, source: str | Path | dict[str, Any]) -> ResolvedSchema:
        """Load from a dict, a path, a raw JSON string, or a URL."""
        if isinstance(source, dict):
            return ResolvedSchema(schema=source, base_uri=str(source.get("$id") or ""), source="<dict>")

        if isinstance(source, Path):
            return self._load_path(source)

        text = str(source).strip()

        if text.startswith("{"):
            try:
                schema = json.loads(text)
            except json.JSONDecodeError as exc:
                raise SchemaResolutionError(f"source is not valid JSON: {exc}") from exc
            base = str(schema.get("$id") or "") if isinstance(schema, dict) else ""
            return ResolvedSchema(schema=schema, base_uri=base, source="<string>")

        if is_url(text):
            return ResolvedSchema(schema=self.fetch(text), base_uri=text, source=text)

        return self._load_path(Path(text))

    def _load_path(self, path: Path) -> ResolvedSchema:
        path = path.expanduser()
        if not path.exists():
            raise SchemaResolutionError(f"schema file not found: {path}")
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SchemaResolutionError(f"{path} is not valid JSON: {exc}") from exc
        uri = path.resolve().as_uri()
        self._memory[uri] = schema
        return ResolvedSchema(schema=schema, base_uri=uri, source=str(path))

    # ------------------------------------------------------------------ fetching

    def fetch(self, uri: str) -> Any:
        """Fetch a document by absolute URI, through the memory then the disk cache."""
        if uri in self._memory:
            return self._memory[uri]

        local = uri_to_path(uri)
        if local is not None:
            if not local.exists():
                raise SchemaResolutionError(f"referenced file not found: {local}")
            try:
                document = json.loads(local.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise SchemaResolutionError(f"{local} is not valid JSON: {exc}") from exc
            self._memory[uri] = document
            return document

        cached = self._read_disk_cache(uri)
        if cached is not None:
            self._memory[uri] = cached
            return cached

        if self.offline:
            raise SchemaResolutionError(f"refusing network fetch (offline): {uri} is not in the cache")

        document = http_get_json(uri, timeout=self.timeout)
        self.fetched.append(uri)
        self._write_disk_cache(uri, document)
        self._memory[uri] = document
        return document

    def _cache_file(self, uri: str) -> Path:
        digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{digest}.json"

    def _read_disk_cache(self, uri: str) -> Any | None:
        target = self._cache_file(uri)
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_disk_cache(self, uri: str, document: Any) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_file(uri).write_text(json.dumps(document), encoding="utf-8")
        except OSError:
            # A failing cache must never fail the run.
            pass

    # ------------------------------------------------------------------ resolving

    def resolve_ref(self, ref: str, base_uri: str) -> tuple[Any, str]:
        """Resolve a ``$ref`` against a base URI, returning the target and its own base URI.

        Handles absolute URLs, relative sibling references (the OO-LD norm) and JSON pointer
        fragments, including a fragment applied to an external document.
        """
        target_uri, _, fragment = ref.partition("#")

        if target_uri:
            absolute = urljoin(base_uri, target_uri) if base_uri else target_uri
            if not is_url(absolute):
                raise SchemaResolutionError(f"cannot resolve relative reference {ref!r} without a base URI")
            document = self.fetch(absolute)
            new_base = absolute
        else:
            document = self.fetch(base_uri) if base_uri else {}
            new_base = base_uri

        if fragment:
            document = apply_json_pointer(document, fragment, ref)

        return document, new_base

    # ------------------------------------------------------------------ dereferencing

    def dereference(self, resolved: ResolvedSchema) -> DereferenceResult:
        """Inline every ``$ref``, producing a graph that may share nodes and contain cycles.

        Targets are memoised by absolute URI and registered *before* their contents are walked,
        so a self-referential schema yields a genuinely circular structure rather than silently
        truncating. :func:`bound_schema` is what makes the result finite again.
        """
        result = DereferenceResult(schema=None)
        memo: dict[str, Any] = {}

        def expand(ref: str, base_uri: str) -> Any:
            absolute = urljoin(base_uri, ref) if base_uri else ref
            if absolute in memo:
                return memo[absolute]

            try:
                target, target_base = self.resolve_ref(ref, base_uri)
            except SchemaResolutionError as exc:
                message = f"{ref}: {exc}"
                if message not in result.unresolved:
                    result.unresolved.append(message)
                return {}

            if absolute not in result.resolved_refs:
                result.resolved_refs.append(absolute)

            if not isinstance(target, dict):
                return inline(target, target_base)

            out: dict[str, Any] = {}
            memo[absolute] = out
            fill(out, target, target_base)
            return out

        def fill(out: dict[str, Any], node: dict[str, Any], base_uri: str) -> None:
            """Populate an already-memoised container with the inlined form of ``node``.

            Split out from :func:`inline` so the memo entry exists before recursion, which is
            what lets a cyclic reference resolve to the (still incomplete) container rather
            than recursing forever.

            The ``$ref`` branch matters more than it looks: a referenced *document* can itself
            be a ``$ref`` node with siblings, which is how the schema.org-derived corpus models
            a refined datatype (``Email.schema.json`` is ``{"$ref": "Text.schema.json",
            "format": "email"}``). Copying such a document's keys verbatim would leave a live
            ``$ref`` in supposedly dereferenced output, and every downstream consumer - the
            validator, the generator - would then fail on an unresolvable reference.
            """
            ref = node.get("$ref")
            if isinstance(ref, str):
                expansion = expand(ref, base_uri)
                if isinstance(expansion, dict):
                    out.update(expansion)
                for key, value in node.items():
                    if key != "$ref":
                        out[key] = inline(value, base_uri)
                return
            for key, value in node.items():
                out[key] = inline(value, base_uri)

        def inline(node: Any, base_uri: str) -> Any:
            if isinstance(node, list):
                return [inline(item, base_uri) for item in node]
            if not isinstance(node, dict):
                return node

            ref = node.get("$ref")
            if isinstance(ref, str):
                expansion = expand(ref, base_uri)
                siblings = {k: v for k, v in node.items() if k != "$ref"}
                if not siblings:
                    return expansion
                # 2020-12 allows $ref to carry siblings; keep them alongside the target.
                inlined = {k: inline(v, base_uri) for k, v in siblings.items()}
                if isinstance(expansion, dict):
                    merged = dict(expansion)
                    merged.update(inlined)
                    return merged
                return inlined

            return {key: inline(value, base_uri) for key, value in node.items()}

        result.schema = inline(resolved.schema, resolved.base_uri)
        return result


def http_get_json_if_changed(uri: str, etag: str | None = None, timeout: float = 10.0) -> tuple[Any | None, str | None]:
    """Fetch JSON unless the caller's copy is still current, returning ``(document, etag)``.

    A ``None`` document means the server answered 304: the caller's copy is byte-identical to
    what the URL serves now, and the returned etag is the one it was validated with. Callers
    that cache a moving target need this to tell "unchanged" from "not checked"; a stored
    timestamp cannot, because it only records when the copy was taken.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    if urlsplit(uri).scheme not in {"http", "https"}:
        raise SchemaResolutionError(f"refusing to fetch a non-http(s) URL: {uri}")

    headers = {"Accept": "application/json", "User-Agent": "oold-validation"}
    if etag:
        headers["If-None-Match"] = etag
    request = Request(uri, headers=headers)  # noqa: S310 - scheme restricted above

    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = response.read().decode("utf-8")
            fresh = response.headers.get("ETag")
    except HTTPError as exc:
        if exc.code == 304:
            return None, etag
        raise SchemaResolutionError(f"could not fetch {uri}: {exc}") from exc
    except (URLError, OSError) as exc:
        raise SchemaResolutionError(f"could not fetch {uri}: {exc}") from exc

    try:
        return json.loads(payload), fresh
    except json.JSONDecodeError as exc:
        raise SchemaResolutionError(f"{uri} did not return valid JSON: {exc}") from exc


def http_get_json(uri: str, timeout: float = 10.0) -> Any:
    """Fetch JSON over HTTP using the standard library, so no HTTP client is a dependency."""
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    # The scheme is checked *before* opening, or `urlopen` would happily read a `file:` (or
    # custom-handler) URL. Local paths have their own code path in `Resolver.fetch`; anything
    # reaching here must be a network fetch.
    if urlsplit(uri).scheme not in {"http", "https"}:
        raise SchemaResolutionError(f"refusing to fetch a non-http(s) URL: {uri}")

    # S310 on both lines: the scheme is restricted to http(s) immediately above.
    request = Request(  # noqa: S310
        uri, headers={"Accept": "application/json", "User-Agent": "oold-validation"}
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            payload = response.read().decode("utf-8")
    except (URLError, OSError) as exc:
        raise SchemaResolutionError(f"could not fetch {uri}: {exc}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SchemaResolutionError(f"{uri} did not return valid JSON: {exc}") from exc


def apply_json_pointer(document: Any, fragment: str, ref: str) -> Any:
    """Walk a JSON pointer fragment such as ``/$defs/Address``."""
    pointer = fragment.lstrip("/")
    if not pointer:
        return document
    current = document
    for raw_token in pointer.split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise SchemaResolutionError(f"could not resolve pointer in {ref!r}")
    return current


# ---------------------------------------------------------------------------- bounding


def bound_schema(root: Any, max_depth: int = DEFAULT_MAX_DEPTH) -> Any:
    """Return a finite, acyclic copy of a dereferenced schema.

    Dereferencing inlines ``$ref``s, so a schema with cyclic embeds (a value type that embeds
    itself, for example schema.org ``QuantitativeValue.valueReference``) becomes a graph with
    circular references, and one where many properties share the same referenced leaf nodes.
    Generation, validation and the variant walker would all recurse without bound. Here a node
    on the current path, or beyond ``max_depth`` instance levels, is cut, and shared nodes are
    memoised so a DAG is not unrolled into an exponentially larger tree. Non-cyclic, shallow
    schemas are copied unchanged.

    Depth counts *instance* nesting rather than raw JSON nesting: an ``allOf``/``anyOf`` hop or a
    subclass chain adds JSON depth without nesting the instance, and counting it would cut
    inherited property constraints - turning them permissive - on any schema a few subclass
    levels deep.

    One subtlety is worth stating explicitly: nesting through ``properties`` does **not** in
    practice consume the budget. The map is enqueued at the current depth alongside its members
    at ``depth + 1``, and when the map is later dequeued it is walked as an ordinary object,
    re-enqueueing those same members at the current depth; the relaxation then keeps the smaller
    value. So only the keywords in :data:`INSTANCE_KEYWORDS` and ``prefixItems`` actually cut on
    depth. Termination does not depend on it either way, since cycles are cut path-locally. This
    is kept deliberately rather than corrected, because it already produces the instance-depth
    semantics described above: making ``properties`` nesting consume the budget too would start
    cutting inherited property constraints on schemas a few subclass levels deep, the exact
    failure the instance-versus-JSON-depth distinction above exists to avoid.
    """
    # Pass 1: each node's minimum instance depth over all paths reaching it. A shared node is
    # then cut, or kept, identically everywhere rather than depending on which path happened to
    # reach it first; otherwise one allOf member can carry an intact copy of a property while
    # another carries an over-cut permissive copy of the same one, and generation satisfies only
    # the cut. Node identity is by object, matching the reference implementation, so `root` must
    # stay alive for the whole call - it does, being the argument.
    min_depth: dict[int, int] = {}
    queue: deque[tuple[Any, int]] = deque([(root, 0)])
    while queue:
        node, depth = queue.popleft()
        if not isinstance(node, (dict, list)):
            continue
        key = id(node)
        if key in min_depth and min_depth[key] <= depth:
            continue
        min_depth[key] = depth

        if isinstance(node, list):
            for item in node:
                queue.append((item, depth))
            continue

        for name, value in node.items():
            step = 1 if (name in INSTANCE_KEYWORDS or name == "prefixItems") else 0
            if name in INSTANCE_MAP_KEYWORDS and isinstance(value, dict):
                queue.append((value, depth))
                for member in value.values():
                    queue.append((member, depth + 1))
            else:
                queue.append((value, depth + step))

    # Pass 2: copy, cutting cycles (path-local) and nodes whose best depth exceeds the budget.
    memo: dict[int, Any] = {}

    def walk(node: Any, path: set[int]) -> Any:
        if not isinstance(node, (dict, list)):
            return node
        key = id(node)
        if key in path:
            return dict(CUT_SCHEMA)  # cycle: the node references itself or an ancestor
        if key in memo:
            return memo[key]  # shared node already bounded: reuse, keeping the DAG
        if min_depth.get(key, 0) > max_depth:
            return dict(CUT_SCHEMA)

        path.add(key)
        out: Any = [] if isinstance(node, list) else {}
        memo[key] = out
        if isinstance(node, list):
            for item in node:
                out.append(walk(item, path))
        else:
            for name, value in node.items():
                if name in IDENTITY_KEYWORDS:
                    continue
                out[name] = walk(value, path)
        path.discard(key)
        return out

    return walk(root, set())


def dereference_and_bound(
    resolver: Resolver, resolved: ResolvedSchema, max_depth: int = DEFAULT_MAX_DEPTH
) -> tuple[Any, DereferenceResult]:
    """Dereference then bound, the combination every instance-level check needs."""
    result = resolver.dereference(resolved)
    return bound_schema(result.schema, max_depth), result
