"""Deterministic instance generation and variant enumeration."""

from __future__ import annotations

from jsonschema import Draft202012Validator

from oold.validation.formats import FORMAT_SAMPLES, OOLD_FORMAT_CHECKER
from oold.validation.generate import DEFAULT_INSTANCE_ID, collect_variants, generate, synth_instance
from oold.validation.resolve import bound_schema


def _validator(schema):
    return Draft202012Validator(schema, format_checker=OOLD_FORMAT_CHECKER)


def test_every_committed_schema_is_satisfiable(resolver, data_dir):
    """The generated instance must validate against the schema that produced it."""
    for path in sorted(data_dir.glob("*.schema.json")):
        schema = bound_schema(resolver.dereference(resolver.load(path)).schema)
        schema.pop("$schema", None)
        result = generate(schema)
        assert result.ok, f"{path.name}: {result.error}"
        errors = list(_validator(schema).iter_errors(result.instance))
        assert not errors, f"{path.name}: {errors[0].message} for {result.instance}"


def test_generation_is_deterministic(resolver, data_dir):
    """A randomised generator turns a round-trip bug into a flaky CI failure."""
    path = data_dir / "PersonWithPet.schema.json"
    schema = bound_schema(resolver.dereference(resolver.load(path)).schema)
    schema.pop("$schema", None)
    assert generate(schema).instance == generate(schema).instance


def test_authored_values_win_in_order():
    result = generate({
        "type": "object",
        "properties": {
            "a": {"const": "C"},
            "b": {"default": "D"},
            "c": {"examples": ["E"]},
            "d": {"enum": ["F", "G"]},
        },
    })
    assert result.instance == {"a": "C", "b": "D", "c": "E", "d": "F"}


def test_declared_formats_are_respected():
    properties = {name: {"type": "string", "format": name} for name in FORMAT_SAMPLES}
    schema = {"type": "object", "properties": properties}
    instance = generate(schema).instance
    assert not list(_validator(schema).iter_errors(instance))


def test_numeric_and_array_bounds_are_respected():
    schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 5},
            "m": {"type": "number", "maximum": -3},
            "a": {"type": "array", "items": {"type": "string"}, "minItems": 2},
        },
    }
    instance = generate(schema).instance
    assert not list(_validator(schema).iter_errors(instance))
    assert len(instance["a"]) == 2


def test_inherited_properties_are_generated():
    """OO-LD models inheritance as allOf, so ignoring it would miss most of a schema."""
    instance = generate({
        "type": "object",
        "properties": {"own": {"type": "string"}},
        "allOf": [{"type": "object", "properties": {"inherited": {"type": "string"}}}],
    }).instance
    assert set(instance) == {"own", "inherited"}


def test_cut_nodes_render_as_distinct_strings():
    """A cut must produce a string.

    At a typeless node a generator is free to emit a boolean or a number, and a non-string
    under an `@type: "@id"` term becomes an RDF literal that cannot compact back, which reads
    as a false round-trip loss. Distinctness matters because in RDF the same IRI is the same
    node, so colliding cuts would merge and change the graph.
    """
    instance = generate({
        "type": "object",
        "properties": {"x": {"format": "x-oold-cut"}, "y": {"format": "x-oold-cut"}},
    }).instance
    assert isinstance(instance["x"], str)
    assert instance["x"] != instance["y"]


def test_generated_ids_are_unique():
    instance = generate({
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "child": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
    }).instance
    assert instance["id"] != instance["child"]["id"]


def test_a_pinned_const_id_is_not_rewritten():
    instance = generate({"type": "object", "properties": {"id": {"const": "ex:fixed"}}}).instance
    assert instance["id"] == "ex:fixed"


def test_cyclic_schema_still_generates(resolver, tmp_path):
    cyclic = {"type": "object", "properties": {}}
    cyclic["properties"]["self"] = cyclic
    result = generate(bound_schema(cyclic))
    assert result.ok
    assert result.notes, "a generated cut should be reported"


def test_variants_are_enumerated_per_branch():
    schema = {
        "type": "object",
        "properties": {"address": {"anyOf": [{"type": "string"}, {"type": "object"}, {"type": "number"}]}},
    }
    variants, total = collect_variants(schema)
    assert total == 3
    assert [v.label for v in variants] == [
        "properties/address/anyOf[0]",
        "properties/address/anyOf[1]",
        "properties/address/anyOf[2]",
    ]
    # Each variant pins exactly one branch, which is what makes the others reachable at all.
    assert variants[1].schema["properties"]["address"]["anyOf"] == [{"type": "object"}]
    # The original is untouched.
    assert len(schema["properties"]["address"]["anyOf"]) == 3


def test_single_branch_alternatives_are_not_variants():
    assert collect_variants({"anyOf": [{"type": "string"}]}) == ([], 0)


def test_variants_are_capped_but_the_total_is_reported():
    schema = {"anyOf": [{"type": "string"}] * 10}
    variants, total = collect_variants(schema, limit=4)
    assert len(variants) == 4
    assert total == 10


def test_each_variant_generates_a_valid_instance(resolver, data_dir):
    path = data_dir / "Contact.schema.json"
    schema = bound_schema(resolver.dereference(resolver.load(path)).schema)
    schema.pop("$schema", None)
    variants, _ = collect_variants(schema)
    assert variants, "Contact.schema.json declares anyOf branches"
    validator = _validator(schema)
    for variant in variants:
        produced = generate(variant.schema)
        assert produced.ok, f"{variant.label}: {produced.error}"
        errors = list(validator.iter_errors(produced.instance))
        assert not errors, f"{variant.label}: {errors[0].message}"


# ------------------------------------------------------------- authored instances


def test_synth_instance_prefers_a_root_level_example():
    """A root-level `examples` entry is a whole example instance, which is what this wants."""
    schema = {"examples": [{"value": 20.1, "unit": "mm"}], "properties": {"value": {"default": 0}}}
    assert synth_instance(schema) == {"@id": DEFAULT_INSTANCE_ID, "value": 20.1, "unit": "mm"}


def test_synth_instance_takes_the_most_derived_example():
    base = {"examples": [{"from": "base"}]}
    derived = {"examples": [{"from": "derived"}]}
    assert synth_instance(derived, [base, derived])["from"] == "derived"


def test_synth_instance_falls_back_to_per_property_examples_defaults_and_enums():
    schema = {
        "properties": {
            "a": {"examples": ["from example"]},
            "b": {"default": "from default"},
            "c": {"enum": ["from enum", "other"]},
            "d": {"type": "string"},
        }
    }
    built = synth_instance(schema)
    assert built["a"] == "from example"
    assert built["b"] == "from default"
    assert built["c"] == "from enum"
    assert "d" not in built


def test_synth_instance_yields_nothing_when_a_required_property_cannot_be_filled():
    """An instance that does not validate is worse than no instance."""
    schema = {"required": ["needed"], "properties": {"other": {"default": 1}, "needed": {"type": "string"}}}
    assert synth_instance(schema) is None


def test_synth_instance_yields_nothing_when_no_value_was_authored():
    assert synth_instance({"properties": {"a": {"type": "string"}}}) is None
    assert synth_instance({}) is None


def test_synth_instance_reads_required_and_properties_across_the_chain():
    base = {"required": ["name"], "properties": {"name": {"default": "x"}}}
    derived = {"properties": {"size": {"default": 1}}}
    assert synth_instance(derived, [base, derived]) == {"@id": DEFAULT_INSTANCE_ID, "name": "x", "size": 1}


def test_synth_instance_writes_the_schema_reference_where_one_is_given():
    schema = {"properties": {"a": {"default": 1}}}
    built = synth_instance(schema, None, "Thing.schema.json")
    assert built["$schema"] == "Thing.schema.json"
    assert built["@context"] == "Thing.schema.json"


def test_synth_instance_omits_the_identity_when_asked():
    built = synth_instance({"properties": {"a": {"default": 1}}}, instance_id=None)
    assert built == {"a": 1}
