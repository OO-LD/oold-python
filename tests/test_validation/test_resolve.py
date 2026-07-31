"""Document loading, $ref dereferencing and schema bounding."""

from __future__ import annotations

import json

import pytest

from oold.validation.resolve import (
    CUT_FORMAT,
    Resolver,
    SchemaResolutionError,
    bound_schema,
)


def test_load_accepts_a_path_a_dict_and_raw_json(resolver, data_dir):
    from_path = resolver.load(data_dir / "Thing.schema.json")
    assert from_path.schema["title"] == "Thing"
    assert from_path.base_uri.startswith("file:")

    from_dict = resolver.load({"$id": "x", "title": "T"})
    assert from_dict.base_uri == "x"

    from_string = resolver.load('{"title": "T"}')
    assert from_string.schema["title"] == "T"


def test_missing_file_is_reported_clearly(resolver):
    with pytest.raises(SchemaResolutionError, match="not found"):
        resolver.load("no-such-file.schema.json")


def test_invalid_json_names_the_file(resolver, tmp_path):
    bad = tmp_path / "bad.schema.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaResolutionError, match="not valid JSON"):
        resolver.load(bad)


def test_offline_refuses_an_uncached_fetch(resolver):
    with pytest.raises(SchemaResolutionError, match="offline"):
        resolver.fetch("https://example.invalid/schema.json")


def test_non_http_urls_are_refused_before_being_opened():
    """`urlopen` would otherwise happily read a `file:` or custom-handler URL."""
    from oold.validation.resolve import http_get_json

    with pytest.raises(SchemaResolutionError, match="non-http"):
        http_get_json("file:///etc/passwd")


def test_file_uris_round_trip_through_uri_to_path(tmp_path, data_dir):
    """Every file URI this package handles comes from `Path.as_uri()`, so both must agree.

    The pre-3.13 branch is hand-rolled, since `url2pathname`'s Windows implementation is
    deprecated from 3.14, so the round-trip is asserted rather than assumed.
    """
    from oold.validation.resolve import uri_to_path

    for target in (tmp_path.resolve(), (data_dir / "Thing.schema.json").resolve()):
        assert uri_to_path(target.as_uri()) == target


def test_uri_to_path_ignores_other_schemes():
    from oold.validation.resolve import uri_to_path

    assert uri_to_path("https://example.org/x.json") is None


def test_dereference_inlines_local_refs(resolver, data_dir):
    loaded = resolver.load(data_dir / "PersonWithPet.schema.json")
    result = resolver.dereference(loaded)
    assert result.unresolved == []
    assert any("Pet.schema.json" in ref for ref in result.resolved_refs)


def test_dereference_resolves_a_document_whose_root_is_a_ref(resolver, tmp_path):
    """A referenced document can itself be `{"$ref": ..., "format": ...}`.

    This is how the schema.org-derived corpus models a refined datatype, and copying such a
    document's keys verbatim would leave a live $ref in supposedly dereferenced output.
    """
    (tmp_path / "Base.schema.json").write_text(
        json.dumps({"$id": "Base.schema.json", "type": "string"}), encoding="utf-8"
    )
    (tmp_path / "Refined.schema.json").write_text(
        json.dumps({"$id": "Refined.schema.json", "$ref": "Base.schema.json", "format": "email"}),
        encoding="utf-8",
    )
    (tmp_path / "Holder.schema.json").write_text(
        json.dumps({
            "$id": "Holder.schema.json",
            "type": "object",
            "properties": {"mail": {"$ref": "Refined.schema.json"}},
        }),
        encoding="utf-8",
    )

    result = resolver.dereference(resolver.load(tmp_path / "Holder.schema.json"))
    mail = bound_schema(result.schema)["properties"]["mail"]
    assert mail == {"type": "string", "format": "email"}
    assert "$ref" not in json.dumps(bound_schema(result.schema))


def test_unresolvable_ref_is_data_not_an_exception(resolver, tmp_path):
    (tmp_path / "A.schema.json").write_text(
        json.dumps({"properties": {"x": {"$ref": "Nope.schema.json"}}}), encoding="utf-8"
    )
    result = resolver.dereference(resolver.load(tmp_path / "A.schema.json"))
    assert result.unresolved
    assert not result.ok


def test_bound_schema_cuts_a_cycle():
    cyclic = {"type": "object", "properties": {}}
    cyclic["properties"]["self"] = cyclic
    out = bound_schema(cyclic)
    assert out["properties"]["self"] == {"format": CUT_FORMAT}
    json.dumps(out)  # must be finite and serialisable


def test_bound_schema_keeps_shared_nodes_intact():
    """A node reached by two paths is shared, not cyclic, and must not be cut."""
    leaf = {"type": "string"}
    out = bound_schema({"type": "object", "properties": {"a": leaf, "b": leaf}})
    assert out["properties"]["a"] == {"type": "string"}
    assert out["properties"]["b"] == {"type": "string"}


def test_bound_schema_drops_identity_keywords():
    out = bound_schema({"$id": "x", "$schema": "y", "type": "object"})
    assert out == {"type": "object"}


def test_composition_hops_do_not_consume_depth():
    """allOf adds JSON depth without nesting the instance.

    Counting it would cut inherited property constraints on any schema a few subclasses deep,
    silently turning them permissive.
    """
    deep = {"allOf": [{"allOf": [{"allOf": [{"allOf": [{"type": "string"}]}]}]}]}
    assert bound_schema(deep, max_depth=2) == deep


def test_items_nesting_consumes_depth():
    nested = {"items": {"items": {"items": {"items": {"type": "string"}}}}}
    out = bound_schema(nested, max_depth=2)
    assert out == {"items": {"items": {"items": {"format": CUT_FORMAT}}}}


def test_properties_nesting_is_depth_neutral():
    """Verified against the reference implementation rather than inferred.

    `properties` enqueues its members at depth+1 but also enqueues the map itself at the
    current depth, and walking that map re-enqueues the members at the lower value, which wins.
    Only the instance keywords actually cut on depth. Reproduced deliberately for parity;
    termination does not rely on it, since cycles are cut path-locally.
    """
    nested = {"properties": {"a": {"properties": {"b": {"properties": {"c": {"type": "string"}}}}}}}
    assert bound_schema(nested, max_depth=2) == nested


def test_disk_cache_is_reused(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    calls = []

    def fake_get(uri, timeout=10.0):
        calls.append(uri)
        return {"title": "Remote"}

    monkeypatch.setattr("oold.validation.resolve.http_get_json", fake_get)

    first = Resolver(cache_dir=cache)
    assert first.fetch("https://example.org/a.json")["title"] == "Remote"
    assert calls == ["https://example.org/a.json"]

    # A fresh resolver with the same cache directory must not fetch again.
    second = Resolver(cache_dir=cache)
    assert second.fetch("https://example.org/a.json")["title"] == "Remote"
    assert calls == ["https://example.org/a.json"], "the disk cache was not reused"
    assert second.fetched == []
