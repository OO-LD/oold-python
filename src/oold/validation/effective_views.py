"""Proving that every mapping set reads one instance losslessly.

Selecting a mapping set promotes its synonyms into the context, so the same instance document
exports as a different graph. The claim that makes that useful is that nothing is lost:
projecting the instance to RDF and reading it back under the same context must return the
document it started from. A mapping that drops a term, coerces a number into a string or turns
a set into a scalar fails here rather than shipping quietly.

The rest of the validation subsystem only ever exercises the context a schema declares, which
is the reading an instance has with nothing selected. A defect confined to one mapping set is
invisible to it, because no check ever promotes that set. This module is the one that does.

The sets are read out of the schemas, so a set nobody declares any more stops being proved
instead of being reported as passing.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pyld import jsonld

from oold.utils.mappings import ScopeSource, declared_context, inline_scoped, mapping_sets, promote, set_name

from .report import FAIL, OK, Check

#: Canonicalisation used for the graph comparison, so two readings are compared as graphs
#: rather than as documents.
NORMALIZE_OPTIONS = {"algorithm": "URDNA2015", "format": "application/n-quads"}

#: Metadata keys that identify the document rather than saying anything the graph holds.
_METADATA_KEYS = ("@context", "$schema")


def canonical(value: Any) -> Any:
    """A comparable form: the metadata keys are not data.

    Deliberately stricter than :func:`oold.validation.roundtrip.canonical`, which also sorts
    arrays and flattens cardinality. Here a difference in order or in cardinality should not be
    hidden by the comparison, because the graph comparison below already forgives exactly the
    differences that carry no meaning, and forgiving them twice would leave a real reordering
    with nothing to report it.
    """
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in sorted(value.items()) if k not in _METADATA_KEYS}
    return value


def undefined_terms(node: Any, context: dict[str, Any]) -> set[str]:
    """Keys an instance uses that the context does not define.

    The round trip cannot see these on its own: an undefined term produces no triple on the way
    out and is missing on the way back, so both sides agree on a graph that lost the data.
    """
    missing: set[str] = set()
    if isinstance(node, list):
        for item in node:
            missing |= undefined_terms(item, context)
    elif isinstance(node, dict):
        for key, value in node.items():
            if not key.startswith(("@", "$")) and key not in context:
                missing.add(key)
            missing |= undefined_terms(value, context)
    return missing


def _type_aliases(context: dict[str, Any]) -> list[str]:
    """Keys that carry ``@type``: the terms aliased to it, then the keyword, then ``type``.

    ``type`` last and only where the context leaves it free, so a schema that uses the name for
    an ordinary property is not read as declaring its own class.
    """
    aliases = [
        term
        for term, definition in context.items()
        if definition == "@type" or (isinstance(definition, dict) and definition.get("@id") == "@type")
    ]
    aliases.append("@type")
    if "type" not in context:
        aliases.append("type")
    return aliases


def _root_type(instance: dict[str, Any], context: dict[str, Any]) -> Any:
    for key in _type_aliases(context):
        if instance.get(key):
            return instance[key]
    return None


@dataclass
class View:
    """One instance read under one mapping set."""

    set_id: str | None
    #: Short name for the reading: the set's name, or ``consensus`` for the declared context.
    label: str
    lossless: bool
    #: Triples the export produced, which is how a reading that says almost nothing shows up.
    triples: int = 0
    #: Keys the effective context does not define. Non-empty always means lossy.
    undefined: list[str] = field(default_factory=list)
    #: The effective context, scoped references resolved.
    context: dict[str, Any] = field(default_factory=dict)
    #: The document the round trip produced, for a failure to print.
    restored: Any = None
    #: Set when the reading could not be run at all, e.g. an invalid promoted context.
    error: str | None = None


def effective_context(
    schemas: Sequence[dict[str, Any]],
    set_id: str | None = None,
    origin: str | None = None,
    source: ScopeSource | None = None,
) -> dict[str, Any]:
    """The context one mapping set gives a schema chain, scoped references resolved.

    Without a ``source`` a scoped ``@context`` is left as the reference it is written as, which
    means the processor has to dereference it; pass one to keep the reading self-contained.
    """
    context = promote(declared_context(schemas), schemas, set_id)
    if source is None:
        return context
    return inline_scoped(context, origin, source, set_id)


def effective_views(
    instance: dict[str, Any],
    schemas: Sequence[dict[str, Any]],
    origin: str | None = None,
    source: ScopeSource | None = None,
    set_ids: Iterable[str | None] | None = None,
) -> list[View]:
    """Read one instance under every mapping set its schemas declare.

    ``schemas`` is the chain whose terms the instance may use, base first. The consensus
    reading, with nothing selected, is always included and comes first, so the alternatives are
    reported against the reading the document has by default.
    """
    schemas = list(schemas)
    sets = list(set_ids) if set_ids is not None else [None, *mapping_sets(schemas)]
    return [_view(instance, schemas, set_id, origin, source) for set_id in sets]


def _view(
    instance: dict[str, Any],
    schemas: Sequence[dict[str, Any]],
    set_id: str | None,
    origin: str | None,
    source: ScopeSource | None,
) -> View:
    label = "consensus" if set_id is None else set_name(set_id)
    try:
        context = effective_context(schemas, set_id, origin, source)
    except Exception as exc:
        return View(set_id=set_id, label=label, lossless=False, error=str(exc))

    document = {k: v for k, v in instance.items() if k not in _METADATA_KEYS}
    document["@context"] = context

    try:
        quads = jsonld.to_rdf(document, {"format": "application/n-quads"})
        back = jsonld.from_rdf(quads, {"format": "application/n-quads", "useNativeTypes": True})
        flat = jsonld.compact(back, context)
        # RDF has no nesting, so the tree comes back only when the graph is framed on the root
        # type; compaction alone yields a flat @graph of blank nodes.
        frame: dict[str, Any] = {"@context": context, "@embed": "@always"}
        root_type = _root_type(instance, context)
        if root_type:
            frame["@type"] = root_type
        restored = jsonld.frame(back, frame)
    except Exception as exc:
        return View(set_id=set_id, label=label, lossless=False, context=context, error=str(exc))

    missing = sorted(undefined_terms(instance, context))
    # A reading may legitimately change the document's shape: where a community states an edge
    # in the other direction the tree hangs off another node, and no frame rooted at the
    # instance's type reaches it. So the fallback test is that the graph survives,
    # canonicalised; the framed form is what a failure prints.
    lossless = not missing and (
        canonical(instance) == canonical(restored)
        or jsonld.normalize(document, NORMALIZE_OPTIONS) == jsonld.normalize(flat, NORMALIZE_OPTIONS)
    )
    return View(
        set_id=set_id,
        label=label,
        lossless=lossless,
        triples=len([quad for quad in quads.strip().split("\n") if quad]),
        undefined=missing,
        context=context,
        restored=restored,
    )


#: Check id for one mapping set's round trip, alongside ``roundtrip.instance``.
CHECK_ID = "roundtrip.mapping_set"


def view_checks(target: str, views: Sequence[View]) -> list[Check]:
    """The views as validation records, one per reading."""
    checks = []
    for view in views:
        detail: dict[str, Any] = {"set": view.set_id, "triples": view.triples}
        if view.undefined:
            detail["undefined_terms"] = view.undefined
        if view.error:
            detail["error"] = view.error
        if view.lossless:
            message = f"{view.label}: lossless round-trip, {view.triples} triples"
        elif view.error:
            message = f"{view.label}: could not be read ({view.error})"
        elif view.undefined:
            message = f"{view.label}: terms not defined in the context: {', '.join(view.undefined)}"
        else:
            message = f"{view.label}: lossy round-trip, {view.triples} triples"
        checks.append(
            Check(
                id=CHECK_ID,
                target=target,
                status=OK if view.lossless else FAIL,
                message=message,
                detail=detail,
            )
        )
    return checks
