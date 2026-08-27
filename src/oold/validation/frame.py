"""Deriving a minimal JSON-LD frame from an OO-LD schema.

Port of ``scripts/schema_to_frame.mjs`` from oold-schema.

Compaction alone reconstructs literals and references from RDF, but an embedded object is
flattened into a separate (blank) node, and compaction never re-nests a flat graph. Framing
does. So a schema that embeds objects needs a frame to round-trip, and this module derives the
minimal one:

* ``@type`` is the schema's instance ``rdf:type``(s), so the exported root - which materialises
  that type - becomes the frame root and embedded objects nest beneath it rather than surfacing
  as sibling graph nodes;
* ``@context`` is the schema's own context, or a reference to it, so terms compact back to their
  property names;
* an empty subframe ``{}`` is added per property that embeds an object.

Reference-valued and literal properties need no subframe: a referenced IRI with no local triples
stays ``{"id": ...}`` and literals compact directly.

Use with ``jsonld.frame(rdf, frame, {"omitDefault": True})`` so a property absent from a given
instance is omitted rather than emitted as null.
"""

from __future__ import annotations

from typing import Any

from .pattern_lint import context_terms

#: Distinguishes "no context reference given" from an explicit ``None``, which is a meaningful
#: JSON-LD context value.
_UNSET = object()


def is_embed(node: Any) -> bool:
    """True when a property's schema describes an embedded *object* value.

    A ``$ref`` alone is not enough: it may point at a scalar DataType leaf, which is a literal
    rather than an embed. After dereferencing, a real embed is inlined as an object with its own
    properties anyway, so the object shape is the reliable signal.
    """
    if not isinstance(node, dict):
        return False
    if node.get("type") == "object" and node.get("properties"):
        return True
    if node.get("items") is not None:
        return is_embed(node["items"])
    for keyword in ("anyOf", "oneOf", "allOf"):
        branches = node.get(keyword)
        if isinstance(branches, list) and any(is_embed(branch) for branch in branches):
            return True
    return False


def collect_composed_properties(node: Any, out: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every property a schema declares, including those inherited through ``allOf``.

    A dereferenced subclass chain inlines each superclass as an ``allOf`` entry, so a schema's
    own ``properties`` map is only part of the picture. First declaration wins, matching the
    reference implementation.
    """
    if out is None:
        out = {}
    if not isinstance(node, dict):
        return out
    for name, value in (node.get("properties") or {}).items():
        if name not in out:
            out[name] = value
    for sub in node.get("allOf") or []:
        collect_composed_properties(sub, out)
    return out


def embedded_properties(schema: dict[str, Any]) -> list[str]:
    """Properties that embed an object, by schema shape or by a scoped ``@context``.

    Shape is the primary signal; a scoped context is a strong hint but not mandatory, since an
    embed can also be mapped by the ambient top-level context.

    A scoped term only counts where the schema declares a property of that name. A schema must
    reflect every ``$ref`` in its ``@context`` (``OOLD-CMP-b926``), including the ones reached
    from ``$defs``, so the context carries terms for properties this schema's instances never
    hold; treating those as embeds puts a property into the derived frame that no instance can
    match, and framing then returns nothing.
    """
    properties = collect_composed_properties(schema)
    structural = [name for name, prop in properties.items() if is_embed(prop)]
    terms = context_terms(schema.get("@context"))
    scoped = [term for term, definition in terms.items() if "@context" in definition and term in properties]
    # dict.fromkeys dedupes while preserving order, matching the JS Set spread.
    return list(dict.fromkeys([*structural, *scoped]))


def instance_rdf_types(schema: Any) -> list[str] | None:
    """The instance ``rdf:type``(s) a schema declares, most-derived-wins.

    Composition is override rather than merge, consistent with ``@context``: the nearest
    declaration in the chain is authoritative, and superclass types stay recoverable by ontology
    inference rather than being materialised. A subclass that wants supertypes in the data lists
    them explicitly. After dereferencing the most-derived value sits at the top level; the
    ``allOf`` walk is the fallback for a subclass that omits its own declaration.
    """
    if not isinstance(schema, dict):
        return None
    own = schema.get("x-oold-instance-rdf-type")
    if isinstance(own, list) and own:
        return own
    if isinstance(schema.get("allOf"), list):
        for sub in schema["allOf"]:
            types = instance_rdf_types(sub)
            if types:
                return types
    return None


def schema_to_frame(schema: dict[str, Any], context_ref: Any = _UNSET) -> dict[str, Any]:
    """Derive the minimal frame for reconstructing this schema's instances.

    ``context_ref``, when given, is used as the frame's ``@context`` in place of the schema's
    inline one. Pass the schema's URL so the document loader resolves inherited and scoped
    contexts rather than losing them.
    """
    frame: dict[str, Any] = {"@embed": "@once"}
    frame["@context"] = schema.get("@context") if context_ref is _UNSET else context_ref
    types = instance_rdf_types(schema)
    if types:
        frame["@type"] = types[0] if len(types) == 1 else types
    for name in embedded_properties(schema):
        frame[name] = {}
    return frame
