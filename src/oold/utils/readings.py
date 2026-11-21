"""Rendering an instance as RDF, once per mapping set.

A reading is what an instance says under one selection. Turtle answers which triples there are;
a reader comparing two mapping sets is usually asking what shape they make, which a diagram
answers at a glance, so both are produced from the same graph.

Two things make a reading reproducible rather than merely correct. Blank nodes are labelled by
URDNA2015 before the graph is built, because a parser assigns fresh identifiers and orders
siblings by them, so without it the same input serialises differently on every run. And every
namespace gets a name: a term of a schema is often a JSON Pointer, Turtle cannot write a slash
in a local name, so the leading part of the pointer becomes a namespace no context declares and
a serializer falls back to ``ns1``, ``ns2``, numbered in the order it happens to meet them.

Nothing here writes a file or assumes a directory. The caller decides where a reading goes.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from oold.utils.mappings import ScopeSource, declared_context, inline_scoped, mapping_sets, promote, set_name

#: Where a canonical blank node label is parked while the graph is built. Blank nodes have to
#: become IRIs for the labels to survive parsing, and this is the IRI space reserved for exactly
#: that (RDF 1.1, skolemisation).
#:
#: A skolem IRI is minted under the authority that publishes the document, so a generator with a
#: site of its own passes ``genid=`` rather than taking this. The default is deliberately not any
#: one publisher's host: a reading rendered here and a reading rendered by a site generator are
#: byte-identical only when both mint under the same authority.
DEFAULT_GENID = "https://oo-ld.org/.well-known/genid/"

#: Pointer segments that carry no meaning of their own, dropped when a namespace is named after
#: the pointer it comes from: ``properties`` and ``$defs`` are how a path into a schema is
#: written, while ``items`` says which thing it reaches and keeps two pointers apart.
POINTER_NOISE = ("properties", "$defs", "definitions")

_C14N_LABEL = re.compile(r"_:(c14n\d+)")


def namespaces(context: dict[str, Any]) -> dict[str, str]:
    """Prefix by namespace IRI, so a node can say which vocabulary it comes from.

    Both spellings count: a term declared with ``@prefix``, and a plain string ending in a
    delimiter, which is how most contexts write one.
    """
    out: dict[str, str] = {}
    for term, definition in context.items():
        if term.startswith("@"):
            continue
        target = definition.get("@id") if isinstance(definition, dict) else definition
        if not isinstance(target, str) or not target.startswith("http"):
            continue
        declared = isinstance(definition, dict) and definition.get("@prefix")
        if declared or target[-1] in "#/":
            out.setdefault(target, term)
    return out


def terms(context: dict[str, Any]) -> dict[str, str]:
    """Term names by IRI, so a schema's own placeholders read as the term that defines them.

    An ontology label is better where there is one, so these are the fallback: a node the
    pinned ontologies do not know still reads as its term name rather than as ``items``.
    """
    prefixes: dict[str, str] = {}
    for term, definition in context.items():
        target = definition.get("@id") if isinstance(definition, dict) else definition
        if not isinstance(target, str) or not target.startswith("http"):
            continue
        if (isinstance(definition, dict) and definition.get("@prefix")) or target[-1] in "#/":
            prefixes[term] = target

    def expand(target: str) -> str:
        head, sep, rest = target.partition(":")
        return prefixes[head] + rest if sep and head in prefixes else target

    out: dict[str, str] = {}
    for term, definition in context.items():
        if term.startswith("@"):
            continue
        target = definition.get("@id") if isinstance(definition, dict) else definition
        if not isinstance(target, str):
            continue
        iri = expand(target)
        if iri.startswith("http") and iri not in out:
            out[iri] = term
    return out


def own(names: dict[str, str], prefix: str) -> dict[str, str]:
    """Keep the term names minted under ``prefix``.

    A term name is what a schema calls something, which is the only name a placeholder of its
    own has. For a term of a real vocabulary the ontology label, or failing that the local name,
    is what a reader expects, so a term name must not override it just because a local alias
    happens to be spelled differently.
    """
    return {iri: name for iri, name in names.items() if iri.startswith(prefix)}


def named_namespaces(
    graph: Any,
    context: dict[str, Any],
    genid: str = DEFAULT_GENID,
    module_base: str | None = None,
    example_hosts: Sequence[str] = ("example.",),
) -> dict[str, str]:
    """Names for the namespaces a serializer would otherwise call ``ns1``, ``ns2``, ...

    A name is derived from what the namespace is: the prefix its schema declares plus the part
    of the pointer that carries meaning, the module it belongs to, or the host it came from. The
    result is legible and the same in every regeneration, which is what lets a build diff its
    own output.

    ``module_base`` is the IRI prefix under which a published identity reads as
    ``<base>/<module>/<version>/``; those namespaces are named after the module. Leave it unset
    where no such space exists.
    """
    from rdflib import URIRef

    declared = namespaces(context)
    module_pattern = re.compile(rf"{re.escape(module_base.rstrip('/'))}/([^/]+)/[^/]+/") if module_base else None
    found: dict[str, str] = {}
    for term in sorted({str(node) for triple in graph for node in triple if isinstance(node, URIRef)}):
        if term.startswith(genid):
            found[genid] = "genid"
            continue
        namespace = term[: max(term.rfind("/"), term.rfind("#")) + 1]
        if not namespace or namespace in declared or namespace in found:
            continue
        module = module_pattern.fullmatch(namespace) if module_pattern else None
        if module:
            # The module's own space, where its schemas are the classes.
            candidate = module[1]
        else:
            base = max((iri for iri in declared if namespace.startswith(iri)), key=len, default=None)
            if base is None:
                # A namespace the data brings with it rather than the schema. An instance used
                # as documentation reads as `ex:`, which is what a reader expects for one.
                host, _, path = namespace.partition("//")[2].partition("/")
                head = "ex" if any(marker in host for marker in example_hosts) else host.split(".")[0]
                candidate = "_".join([head, *[part for part in path.strip("/").split("/") if part]])
            else:
                path = [part for part in namespace[len(base) :].strip("/").split("/") if part]
                rest = [part for part in path if part not in POINTER_NOISE] or path
                candidate = "_".join([declared[base], *rest])
        candidate = re.sub(r"[^A-Za-z0-9_]", "_", candidate)
        while candidate in found.values() or candidate in declared.values():
            candidate += "_"
        found[namespace] = candidate
    return found


def mermaid(graph: Any, labels: dict[str, Any] | None = None, prefixes: dict[str, str] | None = None) -> str:
    """The same reading as a diagram.

    Labels come from the caller, typically harvested from the ontologies a schema maps to, so a
    node reads as its name rather than as an opaque identifier. Which vocabulary a term comes
    from is half of what a reading says, so the prefix is part of the label rather than
    something to infer from a colour.
    """
    from rdflib import RDF, Literal

    labels = labels or {}

    def name(term: Any) -> str:
        text = str(term)
        if isinstance(term, Literal):
            return text
        if "/.well-known/genid/" in text:
            return "blank node"
        known = labels.get(text)
        if known:
            label = known["label"] if isinstance(known, dict) else str(known)
        else:
            label = text.rsplit("#", 1)[-1].rsplit("/", 1)[-1] or text
        for namespace, prefix in sorted((prefixes or {}).items(), key=lambda pair: -len(pair[0])):
            if text.startswith(namespace):
                return f"{prefix}:{label}"
        return label

    types: dict[str, list[str]] = {}
    for subject, _, obj in graph.triples((None, RDF.type, None)):
        types.setdefault(str(subject), []).append(name(obj))

    ids: dict[str, str] = {}
    declarations: list[str] = []
    edges: list[str] = []

    def node(term: Any) -> str:
        key = str(term)
        if key not in ids:
            ids[key] = f"n{len(ids)}"
            label = name(term).replace('"', "'")
            kinds = types.get(key)
            if isinstance(term, Literal):
                declarations.append(f'  {ids[key]}[/"{label}"/]')
            else:
                caption = f"{label}<br>{', '.join(sorted(kinds))}" if kinds else label
                declarations.append(f'  {ids[key]}["{caption}"]')
        return ids[key]

    for subject, predicate, obj in sorted(graph, key=lambda triple: tuple(str(part) for part in triple)):
        if predicate == RDF.type:
            continue
        edges.append(f"  {node(subject)} -->|{name(predicate)}| {node(obj)}")
    return chr(10).join(["flowchart LR", *declarations, *edges])


def skolemised_graph(document: dict[str, Any], genid: str = DEFAULT_GENID) -> Any:
    """The document as an rdflib graph whose blank nodes carry stable labels.

    Canonicalising first (URDNA2015) assigns every blank node a label derived from the data, and
    turning those labels into IRIs is what carries them through the parser, which would
    otherwise replace them with fresh random ones and order siblings by them.
    """
    from pyld import jsonld
    from rdflib import Graph

    nquads = jsonld.normalize(document, {"algorithm": "URDNA2015", "format": "application/n-quads"})
    nquads = _C14N_LABEL.sub(lambda match: f"<{genid}{match[1]}>", nquads)
    return Graph().parse(data=nquads, format="nquads")


def bind_namespaces(graph: Any, context: dict[str, Any], declared: dict[str, str] | None = None, **options: Any) -> Any:
    """Bind every namespace in ``graph`` to a stable prefix, declared or derived.

    ``declared`` overrides the prefixes read from ``context``, for a caller holding a wider map
    than the effective context carries.

    Resolving every term in sorted order afterwards pins the numbering a serializer invents for
    whatever is left to the data rather than to the order it traversed it, which differs between
    machines.
    """
    from rdflib import URIRef

    for iri, prefix in (namespaces(context) if declared is None else declared).items():
        graph.bind(prefix, iri)
    for iri, prefix in named_namespaces(graph, context, **options).items():
        graph.bind(prefix, iri)
    for term in sorted({str(node) for triple in graph for node in triple if isinstance(node, URIRef)}):
        # A term with no split point has no qname and stays written in full.
        with contextlib.suppress(Exception):
            graph.namespace_manager.compute_qname(term)
    return graph


@dataclass
class Reading:
    """One instance rendered under one mapping set."""

    set_id: str | None
    label: str
    context: dict[str, Any] = field(default_factory=dict)
    turtle: str = ""
    diagram: str = ""
    #: Set when the reading could not be rendered, e.g. a promoted context a processor rejects.
    error: str | None = None


def readings(
    instance: dict[str, Any],
    schemas: Sequence[dict[str, Any]],
    origin: str | None = None,
    source: ScopeSource | None = None,
    labels: dict[str, Any] | None = None,
    label_prefix: str | None = None,
    turtle_format: str = "longturtle",
    **options: Any,
) -> list[Reading]:
    """Render an instance to Turtle and a diagram under every mapping set its schemas declare.

    The consensus reading, with nothing selected, comes first. A set whose promoted context a
    processor rejects yields a :class:`Reading` carrying the error instead of failing the run,
    so one broken mapping does not cost the other readings.

    ``options`` are passed to :func:`named_namespaces`; ``label_prefix``, when given, lets a
    schema's own term names stand in as labels for the IRIs minted under it.
    """
    schemas = list(schemas)
    base_context = declared_context(schemas)
    document = {key: value for key, value in instance.items() if key not in ("@context", "$schema")}

    out: list[Reading] = []
    for set_id in [None, *mapping_sets(schemas)]:
        label = "consensus" if set_id is None else set_name(set_id)
        context = promote(base_context, schemas, set_id)
        if source is not None:
            context = inline_scoped(context, origin, source, set_id)
        try:
            graph = skolemised_graph({**document, "@context": context}, options.get("genid", DEFAULT_GENID))
            bind_namespaces(graph, context, {**namespaces(base_context), **namespaces(context)}, **options)
            turtle = graph.serialize(format=turtle_format).strip() + "\n"
        except Exception as exc:
            out.append(Reading(set_id=set_id, label=label, context=context, error=str(exc)))
            continue
        names: dict[str, Any] = {}
        if label_prefix is not None:
            names.update(own(terms(base_context), label_prefix))
            names.update(own(terms(context), label_prefix))
        names.update(labels or {})
        out.append(
            Reading(
                set_id=set_id,
                label=label,
                context=context,
                turtle=turtle,
                diagram=mermaid(graph, names, {**namespaces(base_context), **namespaces(context)}) + chr(10),
            )
        )
    return out
