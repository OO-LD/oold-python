"""The JSON-LD layer: loader, context resolution, framing, round-trip, attribution."""

from __future__ import annotations

import json

import pytest
from pyld import jsonld

from oold.validation.context_resolution import find_alias_keys, resolve_context
from oold.validation.frame import (
    embedded_properties,
    instance_rdf_types,
    is_embed,
    schema_to_frame,
)
from oold.validation.loader import DocumentLoader, describe_jsonld_error
from oold.validation.predicates import check_predicates
from oold.validation.resolve import bound_schema
from oold.validation.roundtrip import (
    canonical,
    canonical_equal,
    is_noop,
    json_equal,
    lost_keys,
    roundtrip,
)

from .conftest import read

# ------------------------------------------------------------------ canonical / lost_keys


def test_scalar_and_single_element_array_are_equivalent():
    """JSON-LD semantics: "x" and ["x"] expand identically.

    Compaction picks one form or the other depending on @container, so cardinality may
    legitimately differ between an instance and its round-trip without any loss.
    """
    assert json_equal(canonical({"a": "x"}), canonical({"a": ["x"]}))


def test_array_order_is_ignored_because_rdf_sets_are_unordered():
    assert json_equal(canonical({"a": ["x", "y"]}), canonical({"a": ["y", "x"]}))


def test_blank_node_ids_are_dropped_but_real_ids_are_kept():
    assert canonical({"@id": "_:b0", "a": 1}) == {"a": [1]}
    assert "@id" in canonical({"@id": "ex:a", "a": 1})


def test_metadata_keys_are_dropped():
    assert canonical({"@context": "x", "$schema": "y", "a": 1}) == {"a": [1]}


def test_json_equal_keeps_booleans_distinct_from_numbers():
    """Python would treat True == 1 as equal; JSON and RDF do not."""
    assert not json_equal(True, 1)
    assert not json_equal([False], [0])
    assert json_equal(1, 1.0)


def test_noop_values_are_not_reported_as_lost():
    assert is_noop(None) and is_noop([]) and is_noop([None, []])
    assert lost_keys({"a": None, "b": []}, {}) == []


def test_lost_keys_reports_missing_keys_with_a_path():
    assert lost_keys({"a": 1}, {}) == ["a"]
    assert lost_keys({"a": {"b": 1}}, {"a": {}}) == ["a.b"]


def test_value_coercion_is_not_a_loss():
    """A reference string resolving to an absolute IRI keeps the key, so it is not a loss."""
    assert lost_keys({"a": "x"}, {"a": "https://example.org/x"}) == []


# ------------------------------------------------------------------ frame derivation


def test_is_embed_requires_an_object_with_properties():
    assert is_embed({"type": "object", "properties": {"a": {}}})
    assert is_embed({"items": {"type": "object", "properties": {"a": {}}}})
    assert is_embed({"anyOf": [{"type": "string"}, {"type": "object", "properties": {"a": {}}}]})
    assert not is_embed({"type": "string"})
    assert not is_embed({"type": "object"})


def test_instance_rdf_types_is_most_derived_wins():
    assert instance_rdf_types({
        "x-oold-instance-rdf-type": ["ex:B"],
        "allOf": [{"x-oold-instance-rdf-type": ["ex:A"]}],
    }) == ["ex:B"]
    # A subclass omitting its own declaration inherits through allOf.
    assert instance_rdf_types({"allOf": [{"x-oold-instance-rdf-type": ["ex:A"]}]}) == ["ex:A"]
    assert instance_rdf_types({"type": "object"}) is None


def test_schema_to_frame_carries_type_context_and_subframes():
    schema = {
        "x-oold-instance-rdf-type": ["schema:Person"],
        "@context": {"ex": "https://example.org/"},
        "properties": {"pet": {"type": "object", "properties": {"name": {}}}},
    }
    frame = schema_to_frame(schema, "https://oo-ld.test/x/P.schema.json")
    assert frame["@embed"] == "@once"
    assert frame["@type"] == "schema:Person"
    assert frame["@context"] == "https://oo-ld.test/x/P.schema.json"
    assert frame["pet"] == {}


def test_schema_to_frame_uses_the_inline_context_when_no_reference_is_given():
    schema = {"@context": {"ex": "https://example.org/"}}
    assert schema_to_frame(schema)["@context"] == {"ex": "https://example.org/"}


def test_embedded_properties_follows_allof_composition():
    schema = {
        "allOf": [{"properties": {"inherited": {"type": "object", "properties": {"x": {}}}}}],
        "properties": {"own": {"type": "string"}},
    }
    assert embedded_properties(schema) == ["inherited"]


# ------------------------------------------------------------------ loader


def test_loader_maps_the_synthetic_base_onto_the_directory(loader, data_dir):
    document = loader(loader.url_for("Thing.schema.json"))["document"]
    assert document["title"] == "Thing"


def test_loader_hands_pyld_a_private_copy(resolver, data_dir):
    """pyld rewrites a retrieved context's relative references to absolute *in place*.

    Returning the cached object would rewrite "Thing.schema.json" to a synthetic URL inside the
    cache, and every later consumer would then fail to resolve it - far from the cause, and only
    when checks happen to run in a particular order.
    """
    loader = DocumentLoader(resolver, directory=data_dir)
    uri = (data_dir / "Person.schema.json").resolve().as_uri()
    before = json.dumps(resolver.fetch(uri)["@context"])

    jsonld.expand(
        {"@context": loader.url_for("Researcher.schema.json"), "@id": "https://example.org/d"},
        loader.options(base=loader.base_url),
    )
    assert json.dumps(resolver.fetch(uri)["@context"]) == before


def test_loader_resolves_a_reference_that_leaves_the_directory(resolver, remote_context_dir):
    """The reference harness cannot do this; its loader only maps names under its own base."""
    loader = DocumentLoader(resolver, directory=remote_context_dir)
    expanded = jsonld.expand(
        {"@context": loader.url_for("Leaf.schema.json"), "name": "Ada"},
        loader.options(base=loader.base_url),
    )
    assert expanded, "the ../Thing.schema.json parent context did not resolve"
    assert "http://schema.org/name" in expanded[0]


def test_loader_refuses_to_escape_its_root(resolver, remote_context_dir):
    loader = DocumentLoader(resolver, directory=remote_context_dir)
    with pytest.raises(jsonld.JsonLdError, match="escapes"):
        loader("https://oo-ld.test/../../../../etc/passwd")


def test_offline_refusal_reaches_the_user(resolver, data_dir):
    """pyld replaces a loader failure with generic text; the real reason must survive."""
    loader = DocumentLoader(resolver, directory=data_dir)
    with pytest.raises(jsonld.JsonLdError) as excinfo:
        jsonld.expand({"@context": "https://example.invalid/c.jsonld", "a": 1}, loader.options())
    assert "offline" in describe_jsonld_error(excinfo.value)


def test_missing_document_names_the_file(resolver, data_dir):
    loader = DocumentLoader(resolver, directory=data_dir)
    with pytest.raises(jsonld.JsonLdError) as excinfo:
        loader(loader.url_for("NoSuchSchema.schema.json"))
    assert "no such document" in describe_jsonld_error(excinfo.value)


# ------------------------------------------------------------------ context resolution


def test_context_chain_is_followed_through_schema_references(resolver, data_dir):
    """OO-LD @context entries point at other schemas, not at context documents."""
    loaded = resolver.load(data_dir / "Researcher.schema.json")
    context = resolve_context(loaded.schema, loaded.base_uri, resolver)
    assert context.errors == []
    # Researcher -> Person -> Thing, so `name` (declared on Thing) must be reachable.
    assert "name" in context.terms()
    assert len(context.resolved_refs) == 2


def test_unresolvable_context_reference_is_reported(resolver, broken_dir):
    loaded = resolver.load(broken_dir / "unresolvable_context_ref.schema.json")
    context = resolve_context(loaded.schema, loaded.base_uri, resolver)
    assert context.errors and "NoSuchSchema" in context.errors[0]


def test_find_alias_keys_discovers_id_and_type_terms():
    assert find_alias_keys({"id": "@id", "type": "@type"}) == ("id", "type")
    assert find_alias_keys({"identifier": {"@id": "@id"}}) == ("identifier", "@type")
    assert find_alias_keys({"name": "ex:name"}) == ("@id", "@type")


# ------------------------------------------------------------------ round-trip


def test_committed_instances_round_trip_losslessly(resolver, data_dir, loader):
    for path in sorted(data_dir.glob("*.instance.json")):
        instance = read(path)
        schema = bound_schema(resolver.dereference(resolver.load(data_dir / instance["$schema"])).schema)
        schema.pop("$schema", None)
        nquads = jsonld.to_rdf(instance, loader.options(base=loader.url_for(path.name), format="application/n-quads"))
        assert nquads.strip(), f"{path.name} produced no triples"
        back = jsonld.from_rdf(nquads, {"format": "application/n-quads", "useNativeTypes": True})
        if embedded_properties(schema):
            restored = jsonld.frame(
                back,
                schema_to_frame(schema, loader.url_for(instance["$schema"])),
                loader.options(base=loader.url_for(path.name), omitDefault=True),
            )
        else:
            restored = jsonld.compact(
                back,
                loader.url_for(instance["$schema"]),
                loader.options(base=loader.url_for(path.name)),
            )
        assert canonical_equal(instance, restored), f"{path.name} did not round-trip"


def test_scalar_instance_round_trips_trivially(loader):
    result = roundtrip({"type": "string"}, "just a string", "https://example.org/c", loader)
    assert result.ok and result.lost == []


def test_roundtrip_reports_a_property_with_no_context_term(resolver, broken_dir):
    loader = DocumentLoader(resolver, directory=broken_dir)
    schema = read(broken_dir / "missing_context_term.schema.json")
    result = roundtrip(
        schema,
        {"name": "Ada", "orphan": "lost"},
        loader.url_for("missing_context_term.schema.json"),
        loader,
    )
    assert result.lost == ["orphan"]
    assert not result.ok


# ------------------------------------------------------------------ predicate attribution


def test_undefined_prefix_is_flagged_as_suspicious():
    """The dangerous case: the key survives and the round-trip is clean, but means nothing."""
    result = check_predicates({"latitude": 51.5}, {"latitude": "schema:latitude"})
    assert result.suspicious == {"latitude": "schema:latitude"}
    assert not result.ok


def test_defined_prefix_is_mapped():
    result = check_predicates({"latitude": 51.5}, {"schema": "https://schema.org/", "latitude": "schema:latitude"})
    assert result.mapped == {"latitude": "https://schema.org/latitude"}
    assert result.ok


def test_property_with_no_term_is_dropped():
    result = check_predicates({"nowhere": 1}, {"other": "https://example.org/other"})
    assert result.dropped == ["nowhere"]


def test_id_alias_is_not_mistaken_for_a_dropped_property():
    """A node carrying only @id is free floating and JSON-LD discards it on expansion.

    The anchor predicate keeps it alive, or a working @id alias would look broken.
    """
    result = check_predicates({"id": "ex:a"}, {"id": "@id"})
    assert result.aliased == {"id": "@id"}
    assert result.ok


def test_undeclared_keys_are_separated_from_dropped_ones():
    result = check_predicates(
        {"known": 1, "extra": 2},
        {"known": "https://example.org/known", "extra": "https://example.org/extra"},
        declared_properties={"known"},
    )
    assert result.undeclared == ["extra"]
    assert result.dropped == []


def test_broken_fixture_reports_its_orphan_property(resolver, broken_dir):
    loaded = resolver.load(broken_dir / "missing_context_term.schema.json")
    context = resolve_context(loaded.schema, loaded.base_uri, resolver)
    result = check_predicates(
        {"name": "Ada", "orphan": "x"}, context.as_jsonld(), declared_properties={"name", "orphan"}
    )
    assert result.dropped == ["orphan"]
