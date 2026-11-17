import pytest
from rdflib import Graph

from .dataset import BASE_TRIPLES, TRIPLE_SIZES, build_person_model, edges_per_person, make_people


@pytest.mark.parametrize("triples", [*TRIPLE_SIZES, 1_001, 1_003])
def test_edge_plan_hits_the_target(triples):
    counts = edges_per_person(triples)
    assert sum(BASE_TRIPLES + edges for edges in counts) == triples


def test_edge_plan_rejects_tiny_datasets():
    with pytest.raises(ValueError):
        edges_per_person(8)


def test_people_are_deterministic_and_loop_free():
    person_cls = build_person_model()
    first = [p.model_dump() for p in make_people(person_cls, 1_001)]
    assert first == [p.model_dump() for p in make_people(person_cls, 1_001)]
    for person in first:
        assert f"perf:{person['name']}" not in person["knows"]
        assert len(set(person["knows"])) == len(person["knows"])


@pytest.mark.parametrize("triples", [1_000, 1_001])
def test_exported_graph_has_exactly_the_target_triples(triples):
    graph = Graph()
    for person in make_people(build_person_model(), triples):
        graph.parse(data=person.to_jsonld(), format="json-ld")
    assert len(graph) == triples
