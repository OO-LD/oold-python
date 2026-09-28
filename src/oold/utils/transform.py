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
    """Parse serialized RDF into an rdflib dataset.

    ``default_union`` is set because the serializers read through
    ``Dataset.triples()``, which without it queries the default graph alone and
    silently drops every quad that sits in a named one.
    """
    from rdflib import Dataset

    dataset = Dataset()
    dataset.default_union = True
    dataset.parse(data=data, format=format)
    return dataset


def _vocab_valued_properties(context: Any) -> set[str]:
    """Property IRIs whose *values* name vocabulary IRIs, from ``@type: @vocab``.

    Only in those positions may an object IRI be a synonym that needs rewriting:
    a value coerced ``@vocab`` is a term drawn from a vocabulary, while an
    ordinary ``@type: @id`` value is a reference to a node and means something
    else entirely. The distinction is a property of the *term definition*, so it
    is read from the context rather than guessed from the data - the spec warns
    that value terms share the context's global term namespace
    (``OOLD-EXT-2542``).
    """
    terms: set[str] = set()

    def scan(node: Any) -> None:
        if isinstance(node, list):
            for part in node:
                scan(part)
            return
        if not isinstance(node, dict):
            return
        for term, definition in node.items():
            if term.startswith("@") or not isinstance(definition, dict):
                continue
            if definition.get("@type") == "@vocab":
                terms.add(term)
            if "@context" in definition:
                scan(definition["@context"])

    scan(context)
    return {iri for iri in (_expand_iri(context, term) for term in terms) if iri}


def _literal_inversion(expanded: Any, invert: dict[str, str]) -> str | None:
    """The first inverted predicate whose object is a literal, if any.

    Inverting exchanges subject and object, and a literal cannot be a subject.
    Left to the processor this surfaces as a flattening error naming nothing;
    checked here it names the predicate.
    """

    def walk(node: Any) -> str | None:
        if isinstance(node, list):
            for item in node:
                found = walk(item)
                if found:
                    return found
            return None
        if not isinstance(node, dict):
            return None
        for key, values in node.items():
            if key in invert:
                for value in values if isinstance(values, list) else [values]:
                    if isinstance(value, dict) and "@value" in value:
                        return key
            found = walk(values)
            if found:
                return found
        return None

    return walk(expanded)


def _rewrite_by_context(
    document: Any,
    context: dict[str, Any],
    swap: dict[str, str],
    invert: dict[str, str],
) -> Any:
    """Rewrite synonyms onto their primary IRIs by manipulating the context.

    One *bridge term* per synonym: compact the document under a context where
    that term denotes the synonym IRI, redefine the same term to denote the
    primary IRI, then flatten and compact under the target context. The document
    keys do not move; what they mean does. Inversion is expressed by the bridge's
    second definition using ``@reverse``, which the processor applies when it
    re-expands.

    This is why the rewrite stays inside JSON-LD. Compaction, flattening and
    expansion are the normative algorithms every conforming JSON-LD Processor
    implements, and a term definition says exactly which positions it governs -
    so a synonym is rewritten as a predicate, as an ``@type`` object, or as a
    ``@vocab``-coerced value, and never in a position that merely happens to
    hold the same IRI. Rewriting the RDF instead loses that: a dataset carries no
    term definitions, so nothing there distinguishes a vocabulary value from a
    reference to a node.

    ``context`` is the chain's declared context, not the document's. A document
    may reference its context remotely, and a bare URL says nothing about which
    terms coerce ``@vocab``.
    """
    if not swap and not invert:
        return jsonld.compact(document, context)

    expanded = jsonld.expand(document)
    offender = _literal_inversion(expanded, invert)
    if offender is not None:
        raise ValueError(f"cannot invert {offender}: the object is a literal, and a literal cannot be a subject")

    source: dict[str, Any] = {}
    target: dict[str, Any] = {}
    for n, (synonym, primary) in enumerate(swap.items()):
        # predicate position ...
        source[f"_p{n}"] = {"@id": synonym}
        target[f"_p{n}"] = {"@id": primary}
        # ... and value position: an @type object, or a @vocab-coerced value
        source[f"_v{n}"] = synonym
        target[f"_v{n}"] = primary
    for n, (synonym, primary) in enumerate(invert.items()):
        source[f"_r{n}"] = {"@id": synonym}
        target[f"_r{n}"] = {"@reverse": primary}
    # Keep the @vocab coercion on those properties so their values compact
    # against the value bridges above, and move the property itself if it is a
    # synonym too.
    for n, iri in enumerate(sorted(_vocab_valued_properties(context))):
        source[f"_c{n}"] = {"@id": iri, "@type": "@vocab"}
        target[f"_c{n}"] = {"@id": swap.get(iri, iri), "@type": "@vocab"}

    bridged = jsonld.compact(expanded, source)
    bridged["@context"] = target
    return jsonld.compact(jsonld.flatten(bridged), context)


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


def _under(instance: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """The instance read under a given context.

    An instance names its schema, not its terms, so the chain's context is
    attached rather than merged: whatever the document carried is replaced, and
    ``$schema`` is dropped because it identifies the schema rather than saying
    anything the graph should hold.
    """
    document = {k: v for k, v in instance.items() if k not in ("@context", "$schema")}
    document["@context"] = context
    return document


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

    nquads = jsonld.to_rdf(_under(instance, context), {**(options or {}), "format": NQUADS})
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

    # A serialized graph is read into JSON-LD first, so the rewrite below always
    # has term definitions to work with. A document handed in as JSON-LD is used
    # as it stands - sending it through RDF and back would cost two conversions
    # and lose what RDF does not carry, such as @index keys and @direction.
    if isinstance(text, (dict, list)):
        document = text
    elif format == JSON_LD:
        document = json.loads(text)
    else:
        nquads = text if format == NQUADS else _dataset(text, "turtle").serialize(format="nquads")
        document = jsonld.from_rdf(nquads, {"format": NQUADS, "useNativeTypes": True})

    # Only one of the two mechanisms may act. Without a named set the synonyms are rewritten
    # onto the primary IRIs and the declared context reads the result. With one, the promoted
    # context already maps those IRIs - and carries the ``@nest`` that decides the shape - so
    # rewriting first would move the predicates out from under it and lose both.
    if set_id is None:
        document = _rewrite_by_context(document, context, *_rewrite_map(schemas, context))

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
    """Read an instance of one schema chain as an instance of another.

    The source chain decides what the document says - a named set promotes one
    reading of it - and the target chain decides how it is said. Both halves are
    context operations, so the instance never leaves JSON-LD: it is handed to
    :func:`from_rdf` as a document rather than as a graph, which is the same path
    a hand-pasted JSON-LD document takes.
    """
    source_schemas = list(source_schemas)
    promoted = promote(declared_context(source_schemas), source_schemas, set_id)
    return from_rdf(_under(instance, promoted), target_schemas)


# ---------------------------------------------------------------------------
# Deprecated: the pre-specification ``"name*"`` notation
# ---------------------------------------------------------------------------
# Kept verbatim, and kept working. The notation below encodes a synonym as a
# sibling key in the context and predates OO-LD; ``x-oold-context`` states the
# same relation with a mapping predicate and a set identifier, and is what the
# meta-schema validates - so new code wants :func:`transform`.
#
# These are reimplemented nowhere: a rewrite over the new core would have to
# reproduce their handling of anonymous documents and of a list-valued document
# context, and any drift there would be a breaking change wearing the clothes of
# a refactor. They go at the next major version instead.


def jsonld_to_jsonld(graph: dict, transformation_context: dict) -> dict:
    """Applies OO-LD alias notation to transform JSON(-LD) documents

    Parameters
    ----------
    graph
        input JSON(-LD) document to transform
    context
        transformation context, which contains the mapping of aliases to URIs

    Returns
    -------
        transformed JSON(-LD) document
    """
    temp1 = {}
    temp2 = {}
    temp3 = {}

    # # not expanded => at least one key is not an IRI
    # expanded = True

    # if "@context" in graph: expanded = False
    # elif "@graph" in graph:
    #     for item in graph["@graph"]:
    #         if not is_iri(item):
    #             expanded = False
    #             break
    # else:
    #     for key in graph.keys():
    #         if not (":" in value):
    #             expanded = False
    #             break

    # if not context is given, we assume the default context
    # if '@context' not in graph:
    #    graph["@context"] = context

    # in case graph is not expanded we expand first
    # graph = jsonld.expand(graph)

    for key, value in transformation_context.items():
        if key.endswith("*"):
            temp1_value = {}
            temp2_value = {}
            if type(value) is dict:
                if "@id" in value:
                    temp1_value["@id"] = value["@id"]
                if "@reverse" in value:
                    temp1_value["@id"] = value["@reverse"]
                if "@type" in value:
                    temp1_value["@type"] = value["@type"]
                temp2_value = {**value}
                # if "@id" in value: del temp2_value["@id"]
                # if "@reverse" in value: del temp2_value["@reverse"]
            else:
                temp1_value["@id"] = value
                temp2_value["@id"] = value

            org_key = key.replace("*", "")
            org_value = transformation_context[org_key]
            if type(org_value) is dict:
                if "@id" in org_value:
                    # temp2_value["@id"] = org_value["@id"]
                    if "@id" in temp2_value:
                        temp2_value["@id"] = org_value["@id"]
                    if "@reverse" in temp2_value:
                        temp2_value["@reverse"] = org_value["@id"]
                # if "@reverse" in org_value: temp2_value["@id"] = org_value["@reverse"]
                else:
                    print("Error")
            else:
                if "@id" in temp2_value:
                    temp2_value["@id"] = org_value
                if "@reverse" in temp2_value:
                    temp2_value["@reverse"] = org_value

            temp1["_" + temp1_value["@id"].replace(":", "_")] = temp1_value
            temp2["_" + temp1_value["@id"].replace(":", "_")] = temp2_value

            temp1[key] = None
            # temp3[org_key] = None

    print("temp1", temp1)
    print("temp2", temp2)
    print("temp3", temp3)
    graph = jsonld.compact(graph, {**transformation_context, **temp1})

    graph["@context"] = {**transformation_context, **temp2}
    graph = jsonld.flatten(graph)  # may introduce blank node @ids
    # graph = jsonld.expand(graph) # does not resolve @reverse relations

    graph = jsonld.compact(graph, {**transformation_context, **temp3})

    return graph


def json_to_json(document: dict, transformation_context: dict, document_context: dict | None = None) -> dict:
    """Applies OO-LD alias notation to transform JSON documents

    Parameters
    ----------
    document
        input JSON document to transform
    transformation_context
        transformation context, which contains the mapping of aliases to URIs
    document_context
        context of the input document. Defaults to transformation_context

    Returns
    -------
        transformed JSON document
    """
    if document_context is None:
        document_context = transformation_context
    if type(document_context) is list:
        document = {"@graph": document}
    document["@context"] = document_context
    document = jsonld.expand(document)
    # anonymous_document = "@id" not in document
    # if "@graph" in document:
    #    # check none of the items in the graph has an @id
    #    anonymous_document = all("@id" not in item for item in document["@graph"])
    # check if json-string contains an @id
    anonymous_document = "@id" not in json.dumps(document)
    document = jsonld_to_jsonld(document, transformation_context)

    if anonymous_document:
        context = document["@context"]
        document = jsonld.expand(document)

        # if "@id" in document:
        #     del document["@id"]
        # if "@graph" in document:
        #     for item in document["@graph"]:
        #         if "@id" in item:
        #             del item["@id"]
        # recursively delete all @id keys in the document
        def remove_ids(d):
            if isinstance(d, dict):
                d.pop("@id", None)
                for key in list(d.keys()):
                    remove_ids(d[key])
            elif isinstance(d, list):
                for item in d:
                    remove_ids(item)

        remove_ids(document)
        document = jsonld.compact(document, context)
    del document["@context"]
    return document
