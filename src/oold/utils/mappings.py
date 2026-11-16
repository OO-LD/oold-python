"""Reading ``x-oold-context`` synonyms into an effective ``@context``.

A term carries one primary mapping in ``@context`` and any number of synonyms in
``x-oold-context``, each keyed by the synonym IRI. Selecting a *mapping set* promotes the
synonyms tagged with it, so the same instance exports as a different graph without the
document changing. Nothing here rewrites an instance; it only decides what the terms mean.

Ported from the generators in `OO-LD/oold-reference-schemas
<https://github.com/OO-LD/oold-reference-schemas>`_ (``scripts/_shared.py`` and
``scripts/build_docs.py``), whose own note says that code was written to move into the OO-LD
core unchanged. Three deliberate differences from that source, and this list is the only one:

* ``mapping_set_id`` may be a list. The specification allows an entry to belong to several
  sets, and the upstream copy only ever saw the string form.
* ``chain`` takes a resolver callable rather than doing ``Path`` arithmetic, so a remote
  ``$ref`` and a browser (Pyodide) environment work the same as a local directory.
* a promoted ``@reverse`` takes the synonym IRI from the entry's key, not from the value the
  fragment writes. ``OOLD-EXT-4966`` has promotion write ``{"@id": <synonym IRI>, ...fragment}``
  and ``OOLD-EXT-7c5d`` has a processor read the synonym IRI, which is the key. A reverse term
  cannot carry ``@id``, so ``@reverse`` is where that IRI goes, and a fragment naming a
  different predicate there contradicts the key it is filed under. The source took the
  fragment's value, which agrees with the key in every mapping written so far.

Semantics follow the OO-LD 1.0.0-rc.2 meta-schema: ``x-oold-sssom.predicate_id`` defaults to
``skos:exactMatch``, and only ``exactMatch`` entries are co-emitted.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

#: The SKOS predicate that makes a synonym interchangeable with the primary term. Other
#: predicates (``closeMatch``, ``broadMatch``, ...) record a weaker relation and are never
#: promoted or rewritten automatically.
SKOS_EXACT_MATCH = "http://www.w3.org/2004/02/skos/core#exactMatch"

_EXACT_MATCH_FORMS = frozenset({"skos:exactMatch", SKOS_EXACT_MATCH})


def set_name(iri: str) -> str:
    """Short name of a mapping set, from its identifier."""
    return iri.rstrip("/").rsplit("/", 1)[-1].removesuffix(".sssom.tsv")


def context_of(schema: dict[str, Any]) -> dict[str, Any]:
    """The inline term definitions of a schema, with a list ``@context`` merged in order."""
    ctx = schema.get("@context")
    if isinstance(ctx, list):
        merged: dict[str, Any] = {}
        for part in ctx:
            if isinstance(part, dict):
                merged.update(part)
        return merged
    return ctx if isinstance(ctx, dict) else {}


def declared_context(schemas: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The consensus context of a chain: every schema's inline terms, base first.

    This is what an instance means with no mapping set selected.
    """
    merged: dict[str, Any] = {}
    for schema in schemas:
        merged.update(context_of(schema))
    return merged


def _set_ids(fragment: dict[str, Any]) -> list[str]:
    """The mapping sets one synonym entry belongs to (the slot may hold a list)."""
    raw = (fragment.get("x-oold-sssom") or {}).get("mapping_set_id")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    return []


def is_exact_match(fragment: dict[str, Any]) -> bool:
    """Whether a synonym entry is an ``exactMatch``, which is the default when unstated."""
    predicate = (fragment.get("x-oold-sssom") or {}).get("predicate_id")
    return predicate is None or predicate in _EXACT_MATCH_FORMS


def synonyms_of(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The ``x-oold-context`` block of one schema, with non-dict entries dropped.

    A ``null`` entry removes an inherited mapping under composition, so it is not a synonym
    to read; it is the absence of one.
    """
    out: dict[str, dict[str, Any]] = {}
    for term, entries in (schema.get("x-oold-context") or {}).items():
        for iri, fragment in (entries or {}).items():
            if isinstance(fragment, dict):
                out.setdefault(term, {})[iri] = fragment
    return out


def mapping_sets(schemas: Iterable[dict[str, Any]]) -> list[str]:
    """Every mapping set the given schemas declare a synonym in.

    Taken over all of them, not just the most derived one: a subschema inherits the mappings
    of what it extends, so a reading exists for a set it never mentions itself.
    """
    found: set[str] = set()
    for schema in schemas:
        for entries in synonyms_of(schema).values():
            for fragment in entries.values():
                found.update(_set_ids(fragment))
    return sorted(found)


def promote(
    base_ctx: dict[str, Any],
    schemas: Iterable[dict[str, Any]],
    set_id: str | None,
) -> dict[str, Any]:
    """The effective ``@context`` for a mapping set.

    Promotes the synonyms tagged with ``set_id`` and leaves every other term on its consensus
    mapping. With no set selected this is the consensus context unchanged.
    """
    ctx = dict(base_ctx)
    if not set_id:
        return ctx
    for schema in schemas:
        for term, entries in synonyms_of(schema).items():
            for iri, fragment in entries.items():
                if set_id not in _set_ids(fragment):
                    continue
                rest = {k: v for k, v in fragment.items() if k != "x-oold-sssom"}
                primary = ctx.get(term)
                # What a term scopes is a property of the shape, not of the vocabulary: the
                # embedded object has the same keys whichever IRI the edge to it carries, and
                # whichever direction it is stated in. So a scoped ``@context`` survives
                # promotion, and the synonym may still override it by carrying its own.
                scoped = (
                    {"@context": primary["@context"]} if isinstance(primary, dict) and "@context" in primary else {}
                )
                if "@reverse" in rest:
                    # The entry is keyed by its IRI either way, but a reverse term carries it
                    # in ``@reverse``; adding ``@id`` as well would not be a valid term
                    # definition.
                    ctx[term] = {**scoped, **rest, "@reverse": iri}
                elif rest:
                    ctx[term] = {"@id": iri, **scoped, **rest}
                else:
                    if isinstance(primary, dict):
                        # Keep the primary's type coercion and container; only the IRI moves.
                        inherited = {k: v for k, v in primary.items() if k != "@id"}
                        ctx[term] = {"@id": iri, **inherited} if inherited else iri
                    else:
                        ctx[term] = iri
                break
    return ctx


def synonym_entries(
    schemas: Iterable[dict[str, Any]],
) -> list[tuple[str, str, dict[str, Any]]]:
    """``(synonym_iri, term, fragment)`` for every ``exactMatch`` synonym in the chain.

    Used for import, where the incoming graph may be written in any of the mapped
    vocabularies - possibly several at once - so a single promoted context cannot express
    what is wanted. The caller expands both sides and rewrites the graph onto the primary
    IRIs instead. Non-``exactMatch`` entries are excluded: a ``closeMatch`` is not a licence
    to treat two predicates as the same.

    The fragment is handed back because a synonym may invert the relation (``@reverse``),
    which is a different rewrite from swapping one predicate for another.
    """
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for schema in schemas:
        for term, synonyms in synonyms_of(schema).items():
            for iri, fragment in synonyms.items():
                if is_exact_match(fragment):
                    entries.append((iri, term, fragment))
    return entries


def chain(
    schema: dict[str, Any],
    resolve: Callable[[str], dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    """A schema's inheritance chain, base first, by following ``allOf`` ``$ref``.

    The mappings need the whole chain: a subschema inherits the terms and the synonyms of
    everything it extends, and reading its own context alone produces an empty graph.

    ``resolve`` turns a ``$ref`` into a schema document and may return ``None`` for one it
    cannot reach, in which case that branch is skipped rather than raising - a playground is
    expected to hold half-written input.

    This is what ``build_docs.inherited`` does in the reference generators, with two limits
    worth knowing. A base reached twice through a diamond ``allOf`` appears once here and twice
    there, since membership is kept on node identity. And an ``allOf`` branch written inline,
    with no ``$ref``, contributes its terms here and is skipped there. Neither case occurs in
    the reference corpus the two were compared on, so the equivalence measured there does not
    cover them.
    """
    out: list[dict[str, Any]] = []
    seen: set[int] = set()

    def walk(node: dict[str, Any]) -> None:
        if not isinstance(node, dict) or id(node) in seen:
            return
        seen.add(id(node))
        for entry in node.get("allOf") or []:
            if not isinstance(entry, dict):
                continue
            ref = entry.get("$ref")
            if isinstance(ref, str) and resolve is not None:
                parent = resolve(ref)
                if parent is not None:
                    walk(parent)
            elif ref is None:
                # An inline allOf branch carries terms of its own.
                walk(entry)
        out.append(node)

    walk(schema)
    return out


class ScopeSource(Protocol):
    """What :func:`inline_scoped` needs in order to follow a scoped ``@context``.

    A scoped ``@context`` names another schema, and resolving that name is the only part of
    the operation that knows where schemas live. Stating it as a protocol keeps this module
    free of any layout: :class:`oold.utils.locator.Locator` implements it over a working tree,
    and a consumer serving schemas from a store or a browser implements it over that instead.

    ``locate`` returns an opaque key identifying a document, or ``None`` for a reference it
    cannot reach. Keys are compared for identity, so a document reached two ways must yield
    one key, which is what makes a cycle detectable.

    ``applicable_schemas`` returns the documents whose ``@context`` and ``x-oold-context``
    apply at that key, base first and the key's own document last.
    """

    def locate(self, target: str, origin: str | None = None) -> str | None: ...

    def applicable_schemas(self, key: str) -> list[dict[str, Any]]: ...


def inline_scoped(
    context: dict[str, Any],
    origin: str | None,
    source: ScopeSource,
    set_id: str | None = None,
    seen: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Replace a term's scoped ``@context`` reference by the context it names.

    A scoped ``@context`` names another schema. Left as a name it has to be dereferenced by
    whoever reads the document, which a processor can only do over the network; resolved here
    against the same source the rest of the build reads, the result is self-contained and the
    version being edited is the one that applies.

    The mapping set applies inside the scope as well. A community reads the whole document and
    not just the root object of it, so a scoped context left on the consensus terms would make
    an embedded object speak a different vocabulary than the tree it hangs in.

    A reference the source cannot reach is left as written, for the consumer to dereference.
    A reference that closes a cycle drops the scoping instead: the terms of a document already
    being read are active anyway, so flattening onto the enclosing context says the same thing
    and terminates.

    A scoped ``@context`` has two valid spellings, both mirroring the ``$ref`` beside it: it
    names the same schema document as a remote context IRI, or it is inlined as a context
    object. A fragment-only reference such as ``"#/$defs/Leaf"`` is neither, and raises. It is
    not a shape worth normalising, because a JSON-LD processor does not read it as one: the
    fragment is ignored and the referenced document's *top-level* ``@context`` is applied, so
    the embedded object silently speaks the enclosing vocabulary instead of its own.
    """
    out: dict[str, Any] = {}
    for term, definition in context.items():
        target = definition.get("@context") if isinstance(definition, dict) else None
        if not isinstance(target, str):
            out[term] = definition
            continue
        if not target.partition("#")[0]:
            raise ValueError(
                f"{term}: a scoped @context must name a schema document or be inlined as a "
                f"context object, but {target!r} is a fragment alone. A processor ignores the "
                f"fragment and applies the named document's top-level @context, so the "
                f"embedded object would take the enclosing vocabulary rather than its own."
            )
        key = source.locate(target, origin)
        if key is None:
            out[term] = definition
            continue
        if key in seen or key == origin:
            out[term] = {k: v for k, v in definition.items() if k != "@context"}
            continue
        schemas = source.applicable_schemas(key)
        nested = promote(declared_context(schemas), schemas, set_id)
        out[term] = {
            **definition,
            "@context": inline_scoped(nested, key, source, set_id, (*seen, key)),
        }
    return out
