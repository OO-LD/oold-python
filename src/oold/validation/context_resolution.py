"""Flattening an OO-LD ``@context`` chain into a plain JSON-LD context.

Most checks reference a context *by URL* and let the document loader fetch it, which keeps
relative IRIs resolving against the right base. An OO-LD schema is itself a valid JSON-LD remote
context - per JSON-LD 1.1, a remote context document only needs a top-level ``@context``, and its
other keys are ignored - so a JSON-LD processor can already follow one straight through, which is
exactly what OO-LD's rule ``OOLD-CMP-b926`` guarantees by requiring a schema to be directly usable
as a context.

What a processor does not expose is the *flattened active context itself* as a value a caller can
inspect. Expanding a document tells you the resulting triples, not which terms were in scope or
where each came from. This module exists for the callers that need that: reporting which terms a
schema defines, and the per-property attribution in :mod:`~oold.validation.predicates`.

``@context`` entries are usually relative siblings, referencing *other OO-LD schemas*::

    "@context": ["StructuredValue.schema.json", {"latitude": "schema:latitude"}]

In the schema.org-derived corpus the prefixes that make those terms meaningful (``schema:``,
``xsd:``) are only defined several hops up the chain, in ``Thing.schema.json``.

The same pattern appears inside term definitions, where a scoped context is also a schema
reference::

    "identifier": {"@id": "schema:identifier", "@context": "PropertyValue.schema.json"}

:func:`resolve_context` walks both forms. Entry order is preserved and the result stays a *list*
of context objects rather than being merged by hand, so JSON-LD's own override semantics still
apply.

Replacing this walk with a JSON-LD processor's own context resolution is worth evaluating, if a
future need exposes that flattened form through a stable API; this module exists because none
does today, not because a processor could not in principle resolve the chain itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from .resolve import Resolver, SchemaResolutionError

#: How deep to follow the inheritance chain (``Thing -> Intangible -> ...``). The chain is
#: linear, so this is only a backstop; cycles are caught by the stack.
DEFAULT_MAX_DEPTH = 40

#: How deep to follow *scoped* contexts nested inside term definitions. These branch rather than
#: chain, so their transitive closure grows explosively and has to be cut much sooner.
#: Truncating one is safe for this module's purpose: scoped contexts govern terms inside nested
#: objects, while the checks here concern a schema's own top-level properties, and the affected
#: term still expands through its ``@id``.
DEFAULT_MAX_SCOPED_DEPTH = 3


@dataclass
class ResolvedContext:
    """A JSON-LD-ready context plus a record of how it was assembled."""

    context: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    resolved_refs: list[str] = field(default_factory=list)
    cut_cycles: list[str] = field(default_factory=list)
    truncated_scoped_contexts: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.context

    def as_jsonld(self) -> Any:
        """The value to use as a document's ``@context``."""
        if not self.context:
            return {}
        if len(self.context) == 1:
            return self.context[0]
        return list(self.context)

    def terms(self) -> dict[str, Any]:
        """Flatten term definitions across all context objects, later entries winning.

        Only used for reporting and for discovering which terms alias ``@id``/``@type``;
        expansion itself always goes through the unflattened context.
        """
        merged: dict[str, Any] = {}
        for entry in self.context:
            if isinstance(entry, dict):
                for key, value in entry.items():
                    if not key.startswith("@"):
                        merged[key] = value
        return merged

    def to_dict(self) -> dict[str, Any]:
        return {
            "term_count": len(self.terms()),
            "errors": self.errors,
            "resolved_refs": self.resolved_refs,
            "cut_cycles": self.cut_cycles,
            "truncated_scoped_contexts": self.truncated_scoped_contexts,
        }


def resolve_context(
    schema: dict[str, Any],
    base_uri: str,
    resolver: Resolver,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_scoped_depth: int = DEFAULT_MAX_SCOPED_DEPTH,
) -> ResolvedContext:
    """Resolve a schema's ``@context`` into a usable JSON-LD context."""
    result = ResolvedContext()
    raw = schema.get("@context")
    if raw is None:
        return result

    _walk_entries(
        raw,
        base_uri,
        resolver,
        result,
        stack=(),
        depth=0,
        max_depth=max_depth,
        scoped_depth=0,
        max_scoped_depth=max_scoped_depth,
    )
    return result


def _walk_entries(
    raw: Any,
    base_uri: str,
    resolver: Resolver,
    result: ResolvedContext,
    stack: tuple[str, ...],
    depth: int,
    max_depth: int,
    scoped_depth: int,
    max_scoped_depth: int,
) -> None:
    """Append the resolved form of a context value onto ``result.context``."""
    entries = raw if isinstance(raw, list) else [raw]

    for entry in entries:
        if isinstance(entry, str):
            _walk_reference(
                entry,
                base_uri,
                resolver,
                result,
                stack,
                depth,
                max_depth,
                scoped_depth,
                max_scoped_depth,
            )
        elif isinstance(entry, dict):
            result.context.append(
                _resolve_inline(
                    entry,
                    base_uri,
                    resolver,
                    result,
                    stack,
                    depth,
                    max_depth,
                    scoped_depth,
                    max_scoped_depth,
                )
            )
        elif entry is None:
            # `null` resets the active context; that is meaningful, so keep it.
            result.context.append(None)
        else:
            result.errors.append(f"unsupported @context entry of type {type(entry).__name__}")


def _walk_reference(
    ref: str,
    base_uri: str,
    resolver: Resolver,
    result: ResolvedContext,
    stack: tuple[str, ...],
    depth: int,
    max_depth: int,
    scoped_depth: int,
    max_scoped_depth: int,
) -> None:
    """Follow a string ``@context`` entry, which points at another OO-LD schema."""
    absolute = urljoin(base_uri, ref) if base_uri else ref

    if absolute in stack:
        if absolute not in result.cut_cycles:
            result.cut_cycles.append(absolute)
        return

    if depth >= max_depth:
        result.errors.append(f"@context chain exceeded depth {max_depth} at {absolute}")
        return

    try:
        document = resolver.fetch(absolute)
    except SchemaResolutionError as exc:
        result.errors.append(f"unresolvable @context reference {ref!r}: {exc}")
        return

    if absolute not in result.resolved_refs:
        result.resolved_refs.append(absolute)

    if isinstance(document, dict) and "@context" in document:
        # An OO-LD schema, or a wrapped context document: recurse into its context, resolving
        # that document's own relative references against its own URI.
        _walk_entries(
            document["@context"],
            absolute,
            resolver,
            result,
            stack=(*stack, absolute),
            depth=depth + 1,
            max_depth=max_depth,
            scoped_depth=scoped_depth,
            max_scoped_depth=max_scoped_depth,
        )
    elif isinstance(document, dict):
        result.context.append(document)  # a bare context object with no wrapper
    else:
        result.errors.append(f"@context reference {ref!r} did not resolve to a JSON object")


def _resolve_inline(
    obj: dict[str, Any],
    base_uri: str,
    resolver: Resolver,
    result: ResolvedContext,
    stack: tuple[str, ...],
    depth: int,
    max_depth: int,
    scoped_depth: int,
    max_scoped_depth: int,
) -> dict[str, Any]:
    """Copy an inline context object, resolving any scoped ``@context`` schema references."""
    resolved: dict[str, Any] = {}

    for term, definition in obj.items():
        if not isinstance(definition, dict) or "@context" not in definition:
            resolved[term] = definition
            continue

        if scoped_depth >= max_scoped_depth:
            # Stop descending, but do not call this an error: the term keeps its `@id` and still
            # expands correctly. Only terms *inside* the nested object lose their scoped
            # definitions, and those are not what this module is consulted for.
            label = f"{term} (in {base_uri.rsplit('/', 1)[-1]})"
            if label not in result.truncated_scoped_contexts:
                result.truncated_scoped_contexts.append(label)
            trimmed = dict(definition)
            trimmed.pop("@context", None)
            resolved[term] = trimmed
            continue

        scoped = ResolvedContext()
        _walk_entries(
            definition["@context"],
            base_uri,
            resolver,
            scoped,
            stack=stack,
            depth=depth + 1,
            max_depth=max_depth,
            scoped_depth=scoped_depth + 1,
            max_scoped_depth=max_scoped_depth,
        )

        # Fold the nested findings into the parent report.
        for ref in scoped.resolved_refs:
            if ref not in result.resolved_refs:
                result.resolved_refs.append(ref)
        for cycle in scoped.cut_cycles:
            if cycle not in result.cut_cycles:
                result.cut_cycles.append(cycle)
        for truncated in scoped.truncated_scoped_contexts:
            if truncated not in result.truncated_scoped_contexts:
                result.truncated_scoped_contexts.append(truncated)
        result.errors.extend(scoped.errors)

        merged = dict(definition)
        if scoped.is_empty:
            # Dropping an unusable scoped context beats leaving a schema reference behind: the
            # term still expands through its own `@id`.
            merged.pop("@context", None)
        else:
            merged["@context"] = scoped.as_jsonld()
        resolved[term] = merged

    return resolved


def find_alias_keys(terms: dict[str, Any]) -> tuple[str, str]:
    """Find which context terms alias ``@id`` and ``@type``.

    OO-LD schemas conventionally expose these as plain ``id`` and ``type`` properties, so the
    actual names have to be discovered rather than assumed. Generation must leave them alone: a
    random string in ``type`` would produce a meaningless RDF type and a false failure.
    """
    id_key, type_key = "@id", "@type"
    for term, definition in terms.items():
        target = definition.get("@id") if isinstance(definition, dict) else definition
        if target == "@id":
            id_key = term
        elif target == "@type":
            type_key = term
    return id_key, type_key
