"""Rendering an instance as RDF under each mapping set.

What these pin down is reproducibility: the same input must serialise to the same bytes on
every run and on every machine, because the output is committed and diffed. Blank node labels
and invented namespace prefixes are the two things that otherwise drift.
"""

import pytest

from oold.utils.readings import (
    DEFAULT_GENID,
    bind_namespaces,
    mermaid,
    named_namespaces,
    namespaces,
    own,
    readings,
    skolemised_graph,
    terms,
)

SET_A = "https://example.org/sets/emmo.sssom.tsv"

SCHEMA = {
    "@context": {
        "ex": "https://example.org/",
        "other": "https://other.example/vocab#",
        "id": "@id",
        "type": "@type",
        "name": "ex:name",
        "part": {"@id": "ex:part"},
    },
    "x-oold-context": {"name": {"other:label": {"x-oold-sssom": {"mapping_set_id": SET_A}}}},
}

INSTANCE = {"@id": "https://example.org/thing", "type": "ex:Thing", "name": "a name"}


def test_namespaces_reads_both_spellings_of_a_prefix():
    context = {
        "ends_in_slash": "https://a.example/",
        "ends_in_hash": "https://b.example#",
        "declared": {"@id": "https://c.example/x", "@prefix": True},
        "plain_term": "https://d.example/term",
        "@vocab": "https://e.example/",
    }
    assert namespaces(context) == {
        "https://a.example/": "ends_in_slash",
        "https://b.example#": "ends_in_hash",
        "https://c.example/x": "declared",
    }


def test_terms_names_an_iri_by_the_term_that_defines_it():
    context = {"ex": "https://example.org/", "name": "ex:name", "other": {"@id": "ex:other"}}
    assert terms(context)["https://example.org/name"] == "name"
    assert terms(context)["https://example.org/other"] == "other"


def test_terms_keeps_the_first_name_for_an_iri_named_twice():
    context = {"ex": "https://example.org/", "first": "ex:same", "second": "ex:same"}
    assert terms(context)["https://example.org/same"] == "first"


def test_own_keeps_only_the_names_minted_under_the_prefix():
    names = {"https://mine.example/a": "a", "https://theirs.example/b": "b"}
    assert own(names, "https://mine.example/") == {"https://mine.example/a": "a"}


def test_a_reading_is_produced_for_the_consensus_and_every_declared_set():
    produced = readings(INSTANCE, [SCHEMA])
    assert [reading.label for reading in produced] == ["consensus", "emmo"]
    assert all(reading.error is None for reading in produced)


def test_a_promoted_set_changes_the_predicate_in_the_turtle():
    produced = {reading.label: reading for reading in readings(INSTANCE, [SCHEMA])}
    assert "ex:name" in produced["consensus"].turtle
    assert "other:label" in produced["emmo"].turtle
    assert "ex:name" not in produced["emmo"].turtle


def test_the_same_input_serialises_to_the_same_bytes_twice():
    first = readings(INSTANCE, [SCHEMA])[0]
    second = readings(INSTANCE, [SCHEMA])[0]
    assert first.turtle == second.turtle
    assert first.diagram == second.diagram


def test_a_blank_node_keeps_a_canonical_label_across_runs():
    """A parser assigns fresh identifiers, so without skolemisation the output drifts."""
    instance = {"type": "ex:Thing", "part": {"name": "nested"}}
    first = readings(instance, [SCHEMA])[0].turtle
    second = readings(instance, [SCHEMA])[0].turtle
    assert first == second
    assert "genid" in first


def test_a_mapping_a_processor_rejects_is_reported_rather_than_raised():
    schema = {
        "@context": {"ex": "https://example.org/", "name": "ex:name"},
        "x-oold-context": {"name": {"other:label": {"@type": "not-an-iri", "x-oold-sssom": {"mapping_set_id": SET_A}}}},
    }
    produced = {reading.label: reading for reading in readings({"name": "x"}, [schema])}
    assert produced["consensus"].error is None
    assert produced["emmo"].error
    assert produced["emmo"].turtle == ""


def test_named_namespaces_names_a_pointer_after_the_prefix_its_schema_declares():
    """A term is a JSON Pointer, and Turtle cannot write a slash in a local name."""
    base = "https://w3id.org/oo-ld/schemas/materials/0.1/Chemical.schema.json#"
    context = {"chem": {"@id": base, "@prefix": True}}
    graph = skolemised_graph({
        "@context": {"@vocab": f"{base}/properties/parts/items/"},
        "@id": "https://example.org/x",
        "constituent": "value",
    })
    assert named_namespaces(graph, context)[f"{base}/properties/parts/items/"] == "chem_parts_items"


def test_named_namespaces_calls_an_example_host_ex():
    graph = skolemised_graph({"@id": "https://example.org/data/thing", "https://example.org/data/p": "v"})
    assert named_namespaces(graph, {})["https://example.org/data/"] == "ex_data"


def test_named_namespaces_names_a_module_space_after_its_module():
    base = "https://w3id.org/oo-ld/schemas"
    graph = skolemised_graph({"@id": "https://example.org/x", "@type": f"{base}/quantities/0.2/Length.schema.json"})
    found = named_namespaces(graph, {}, module_base=base)
    assert found[f"{base}/quantities/0.2/"] == "quantities"


def test_named_namespaces_never_reuses_a_name():
    graph = skolemised_graph({
        "@id": "https://example.org/x",
        "https://a.example/p": "v",
        "https://a.example/sub/p": "v",
    })
    found = named_namespaces(graph, {})
    assert len(set(found.values())) == len(found)


def test_a_genid_node_is_not_given_a_namespace_name_of_its_own():
    graph = skolemised_graph({"@id": "https://example.org/x", "https://a.example/p": {"https://a.example/q": "v"}})
    assert named_namespaces(graph, {}).get(DEFAULT_GENID) == "genid"


def test_mermaid_declares_a_node_per_term_and_an_edge_per_triple():
    graph = skolemised_graph({
        "@id": "https://example.org/x",
        "@type": "https://example.org/Thing",
        "https://example.org/p": "v",
    })
    diagram = mermaid(graph)
    assert diagram.startswith("flowchart LR")
    assert diagram.count("-->") == 1
    assert '[/"v"/]' in diagram


def test_mermaid_prefers_a_supplied_label_and_prefixes_it():
    graph = skolemised_graph({"@id": "https://example.org/x", "https://other.example/p": "v"})
    diagram = mermaid(graph, {"https://other.example/p": {"label": "has part"}}, {"https://other.example/": "other"})
    assert "other:has part" in diagram


def test_mermaid_names_a_blank_node_as_one():
    graph = skolemised_graph({"https://example.org/p": {"https://example.org/q": "v"}})
    assert "blank node" in mermaid(graph)


def test_bind_namespaces_binds_the_declared_prefixes_and_names_the_rest():
    graph = skolemised_graph({"@id": "https://example.org/x", "https://other.example/vocab#p": "v"})
    bind_namespaces(graph, {"other": "https://other.example/vocab#"})
    bound = dict(graph.namespaces())
    assert str(bound["other"]) == "https://other.example/vocab#"
    assert "ex" in bound


@pytest.mark.parametrize("fmt", ["turtle", "longturtle"])
def test_the_turtle_flavour_is_the_callers_choice(fmt):
    assert readings(INSTANCE, [SCHEMA], turtle_format=fmt)[0].turtle.strip()


def test_the_genid_authority_is_the_callers_and_shows_in_the_output():
    """A skolem IRI is minted under whoever publishes the document, so it is a parameter."""
    instance = {"type": "ex:Thing", "part": {"name": "nested"}}
    default = readings(instance, [SCHEMA])[0].turtle
    mine = readings(instance, [SCHEMA], genid="https://schemas.example.org/.well-known/genid/")[0].turtle
    assert DEFAULT_GENID in default
    assert DEFAULT_GENID not in mine
    assert "https://schemas.example.org/.well-known/genid/" in mine


def test_readings_resolves_a_scoped_context_when_a_source_is_given():
    """Without the source the term keeps a bare reference, and the embedded keys reach no triple."""

    class Source:
        def locate(self, target, origin=None):
            return target if target == "Leaf.schema.json" else None

        def applicable_schemas(self, key):
            return [{"@context": {"leaf": "https://vocab.example/leaf"}}]

    schema = {
        "@context": {
            "ex": "https://example.org/",
            "id": "@id",
            "part": {"@id": "ex:part", "@context": "Leaf.schema.json"},
        }
    }
    instance = {"@id": "https://example.org/thing", "part": {"leaf": "a value"}}

    without = readings(instance, [schema])[0]
    with_source = readings(instance, [schema], origin="Root.schema.json", source=Source())[0]

    assert with_source.context["part"]["@context"] == {"leaf": "https://vocab.example/leaf"}
    assert "a value" in with_source.turtle
    assert "a value" not in without.turtle


def test_a_schemas_own_term_names_stand_in_as_labels_under_the_given_prefix():
    """A placeholder of this library has no ontology label, so its term name is the only one."""
    own_base = "https://w3id.org/oo-ld/schemas/materials/0.1/"
    schema = {
        "@context": {
            "own": {"@id": own_base, "@prefix": True},
            "id": "@id",
            "ChemicalComponent": "own:EMMO_1234",
            "part": {"@id": "own:EMMO_5678", "@type": "@id"},
        }
    }
    instance = {"@id": "https://example.org/x", "@type": "own:EMMO_1234", "part": "https://example.org/y"}

    without = readings(instance, [schema])[0].diagram
    with_names = readings(instance, [schema], label_prefix=own_base)[0].diagram

    assert "own:EMMO_1234" in without
    assert "own:ChemicalComponent" in with_names
    assert "own:part" in with_names


def test_named_namespaces_never_shadows_a_prefix_the_context_declares():
    """The derived name for example.org is `ex`, which here is already taken."""
    graph = skolemised_graph({"@id": "https://example.org/data/thing", "https://example.org/data/p": "v"})
    found = named_namespaces(graph, {"ex": "https://other.example/"})
    assert found["https://example.org/data/"] == "ex_data"

    graph = skolemised_graph({"@id": "https://example.org/thing", "https://example.org/p": "v"})
    found = named_namespaces(graph, {"ex": "https://other.example/"})
    assert found["https://example.org/"] == "ex_"


def test_terms_skips_a_keyword_and_a_non_string_target():
    assert terms({"@vocab": "https://a.example/", "broken": {"@id": None}, "ok": "https://a.example/ok"}) == {
        "https://a.example/ok": "ok"
    }
