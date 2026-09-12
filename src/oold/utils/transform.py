"""Carrying an instance between schemas through RDF.

An OO-LD instance is exported to RDF under the ``@context`` its schema declares, optionally
with one mapping set promoted (see :mod:`oold.utils.mappings`). Reading that graph back under
a *different* schema is what makes two vocabularies interoperate: the graph is the interchange
format, and the schemas are the two readings of it.

Export needs a mapping set, because a document has one reading at a time. Import does not:
an incoming graph may use any of the mapped vocabularies, and may mix them, so instead of
guessing a set the importer rewrites every ``exactMatch`` synonym onto the term's primary IRI
and then compacts once. That is why :func:`from_rdf` takes no ``set_id``.

Replaces an earlier implementation that encoded synonyms as ``"name*"`` sibling keys in the
context. That notation predates the specification; ``x-oold-context`` (OO-LD 1.0.0-rc.2)
expresses the same relation with a mapping predicate and a set identifier, and is what the
meta-schema validates.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pyld import jsonld

from oold.utils.mappings import declared_context, promote, synonym_entries

#: Serializations accepted and produced.
TURTLE = "text/turtle"
JSON_LD = "application/ld+json"
NQUADS = "application/n-quads"

_RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _expand_iri(context: Any, value: str) -> str | None:
    """The absolute IRI ``value`` denotes under ``context``.

    Terms and CURIEs are resolved by expanding a probe document, so prefix definitions and
    aliases in the context are honoured rather than reimplemented here. An absolute IRI
    passes through unchanged.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        expanded = jsonld.expand({"@context": context, value: "probe"})
    except Exception:
        return None
    if not expanded:
        return None
    for key in expanded[0]:
        if not key.startswith("@"):
            return key
    return None


def _rewrite_map(schemas: Iterable[dict[str, Any]], context: Any) -> tuple[dict[str, str], dict[str, str]]:
    """Synonym-to-primary IRI rewrites, split by direction.

    Returns ``(swap, invert)``: ``swap`` replaces a predicate in place, ``invert`` does the
    same but also exchanges subject and object, because a ``@reverse`` synonym states the
    relation the other way round (``person worksFor org`` is ``org employs person``).

    An entry is dropped when either side does not expand to an absolute IRI: a term the
    context never defines cannot be rewritten onto anything meaningful.
    """
    swap: dict[str, str] = {}
    invert: dict[str, str] = {}
    for synonym, term, fragment in synonym_entries(schemas):
        source = _expand_iri(context, synonym)
        target = _expand_iri(context, term)
        if not source or not target:
            continue
        if "@reverse" in fragment:
            invert[source] = target
        elif source != target:
            swap[source] = target
    return swap, invert


def _dataset(data: str, format: str):
    """Parse serialized RDF into an rdflib dataset."""
    from rdflib import Dataset

    dataset = Dataset()
    dataset.parse(data=data, format=format)
    return dataset


def _apply_rewrites(nquads: str, swap: dict[str, str], invert: dict[str, str]) -> str:
    """Rewrite synonym predicates, inverted relations and ``rdf:type`` objects.

    Done in RDF rather than by choosing a context, because a graph may use several mapped
    vocabularies at once and a single context can only give each term one reading.
    """
    if not swap and not invert:
        return nquads

    from rdflib import URIRef

    dataset = _dataset(nquads, "nquads")
    forward = {URIRef(k): URIRef(v) for k, v in swap.items()}
    reverse = {URIRef(k): URIRef(v) for k, v in invert.items()}
    rdf_type = URIRef(_RDF_TYPE)

    for graph in list(dataset.graphs()):
        for subject, predicate, obj in list(graph):
            if predicate in reverse:
                graph.remove((subject, predicate, obj))
                graph.add((obj, reverse[predicate], subject))
                continue
            new_predicate = forward.get(predicate, predicate)
            # A class synonym appears as the object of rdf:type, not as a predicate.
            new_object = forward.get(obj, obj) if predicate == rdf_type else obj
            if new_predicate == predicate and new_object == obj:
                continue
            graph.remove((subject, predicate, obj))
            graph.add((subject, new_predicate, new_object))

    return dataset.serialize(format="nquads")


def _strip_blank_ids(node: Any, id_keys: frozenset[str]) -> Any:
    """Drop blank-node identifiers introduced by the RDF round-trip.

    A document that named nothing comes back carrying ``_:b0``-style labels, which are an
    artefact of serializing to triples rather than anything the author wrote. Real IRIs are
    left alone, so identity the input actually declared survives.
    """
    if isinstance(node, list):
        return [_strip_blank_ids(item, id_keys) for item in node]
    if not isinstance(node, dict):
        return node
    return {
        key: _strip_blank_ids(value, id_keys)
        for key, value in node.items()
        if not (key in id_keys and isinstance(value, str) and value.startswith("_:"))
    }


def _id_keys(context: Any) -> frozenset[str]:
    """``@id`` and every term aliased to it, which is how a compacted node names itself."""
    keys = {"@id"}
    if isinstance(context, dict):
        keys.update(term for term, value in context.items() if value == "@id")
    return frozenset(keys)


def _is_graph_document(document: Any) -> bool:
    """Whether a JSON-LD document is a graph of nodes rather than a single node."""
    if isinstance(document, list):
        return len(document) > 1
    return isinstance(document, dict) and "@graph" in document


def to_rdf(
    instance: dict[str, Any],
    schemas: Iterable[dict[str, Any]],
    set_id: str | None = None,
    format: str = TURTLE,
    options: dict[str, Any] | None = None,
) -> str:
    """Export an instance as RDF under the schema chain's effective context.

    ``schemas`` is the inheritance chain, base first (see :func:`oold.utils.mappings.chain`).
    ``set_id`` selects a mapping set; without one the consensus context is used.
    """
    schemas = list(schemas)
    context = promote(declared_context(schemas), schemas, set_id)

    document = {k: v for k, v in instance.items() if k not in ("@context", "$schema")}
    document["@context"] = context

    nquads = jsonld.to_rdf(document, {**(options or {}), "format": NQUADS})
    if format == NQUADS:
        return nquads
    if format == JSON_LD:
        back = jsonld.from_rdf(nquads, {"format": NQUADS, "useNativeTypes": True})
        return json.dumps(jsonld.compact(back, context), indent=2)
    return _dataset(nquads, "nquads").serialize(format="turtle")


def from_rdf(
    text: str | dict[str, Any] | list[Any],
    schemas: Iterable[dict[str, Any]],
    format: str = TURTLE,
    frame: dict[str, Any] | None = None,
    set_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> Any:
    """Read RDF back as an instance of the given schema chain.

    Every ``exactMatch`` synonym the chain declares is honoured, so the graph may be written
    in any of the mapped vocabularies without naming a mapping set. A graph of several nodes
    is reconstructed by framing - compaction alone never re-nests a flat graph - using
    ``frame`` when given, otherwise the frame derived from the most derived schema.

    ``set_id`` is only needed to bridge document *shapes*. Renaming a term is a rewrite of the
    graph and needs no selection, but a promoted fragment may also carry ``@nest``, which
    decides where in the document a value sits rather than what it means. ``@nest`` is a term
    definition and only takes effect when the document is compacted against a context that
    contains it, so a reading that regroups the document has to be named. See
    https://github.com/OO-LD/oold-schema/issues/135.
    """
    schemas = list(schemas)
    context = promote(declared_context(schemas), schemas, set_id)

    if isinstance(text, (dict, list)):
        nquads = jsonld.to_rdf(text, {"format": NQUADS})
    elif format == JSON_LD:
        nquads = jsonld.to_rdf(json.loads(text), {"format": NQUADS})
    elif format == NQUADS:
        nquads = text
    else:
        nquads = _dataset(text, "turtle").serialize(format="nquads")

    # Only one of the two mechanisms may act. Without a named set the synonyms are rewritten
    # onto the primary IRIs and the declared context reads the result. With one, the promoted
    # context already maps those IRIs - and carries the ``@nest`` that decides the shape - so
    # rewriting first would move the predicates out from under it and lose both.
    if set_id is None:
        nquads = _apply_rewrites(nquads, *_rewrite_map(schemas, context))
    document = jsonld.from_rdf(nquads, {"format": NQUADS, "useNativeTypes": True})

    if frame is None and _is_graph_document(document) and schemas:
        from oold.validation.frame import schema_to_frame

        frame = schema_to_frame(schemas[-1], context)

    if frame is not None:
        result = jsonld.frame(document, frame, {**(options or {}), "omitDefault": True})
    else:
        result = jsonld.compact(document, context, {**(options or {})})
    return _strip_blank_ids(result, _id_keys(context))


def transform(
    instance: dict[str, Any],
    source_schemas: Iterable[dict[str, Any]],
    target_schemas: Iterable[dict[str, Any]],
    set_id: str | None = None,
) -> Any:
    """Read an instance of one schema chain as an instance of another, through RDF.

    The two hops are exactly :func:`to_rdf` and :func:`from_rdf`, so a transformation and a
    hand-pasted graph take the same path and cannot diverge in behaviour.
    """
    return from_rdf(
        to_rdf(instance, source_schemas, set_id=set_id, format=NQUADS),
        target_schemas,
        format=NQUADS,
    )
