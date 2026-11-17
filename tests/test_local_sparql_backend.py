"""Pins the observable behaviour of LocalSparqlBackend, so its internals can be optimized."""

import json

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.compare import isomorphic

from oold.backend.sparql import LocalSparqlBackend, _construct_node

EX = "https://example.com/"
NAME = URIRef("https://schema.org/name")
KNOWS = URIRef("https://schema.org/knows")


def _doc(name, knows=(), label=None):
    doc = {"@id": EX + name, str(NAME): [{"@value": label or name}]}
    if knows:
        doc[str(KNOWS)] = [{"@id": EX + other} for other in knows]
    return doc


def _backend(*docs):
    backend = LocalSparqlBackend()
    for doc in docs:
        backend.store_jsonld_dicts({doc["@id"]: doc})
    return backend


def _as_graph(jsonld_dict) -> Graph:
    graph = Graph()
    graph.parse(data=json.dumps(jsonld_dict), format="json-ld")
    return graph


def test_store_replaces_the_previous_triples_of_a_subject():
    backend = _backend(_doc("a", knows=["b"]))
    backend.store_jsonld_dicts({EX + "a": _doc("a", label="renamed")})
    assert set(backend.graph.predicate_objects(URIRef(EX + "a"))) == {(NAME, Literal("renamed"))}


def test_store_leaves_other_subjects_alone():
    backend = _backend(_doc("a"), _doc("b", knows=["a"]))
    backend.store_jsonld_dicts({EX + "a": _doc("a")})
    assert len(backend.graph) == 3


def test_store_twice_is_idempotent():
    backend = _backend(_doc("a", knows=["b"]))
    before = len(backend.graph)
    backend.store_jsonld_dicts({EX + "a": _doc("a", knows=["b"])})
    assert len(backend.graph) == before


def test_resolve_accepts_full_iris_and_the_ex_prefix():
    backend = _backend(_doc("a"))
    by_iri = backend.resolve_iris([EX + "a"])[EX + "a"]
    assert backend.resolve_iris(["ex:a"])["ex:a"] == by_iri
    assert by_iri["@id"] == EX + "a"


def test_resolve_returns_one_entry_per_requested_iri():
    backend = _backend(_doc("a"), _doc("b"), _doc("c"))
    assert list(backend.resolve_iris([EX + "c", EX + "a"])) == [EX + "c", EX + "a"]


def test_resolve_matches_the_sparql_construct_it_replaces():
    backend = _backend(_doc("a", knows=["b", "c"]), _doc("b", knows=["a"]), _doc("c"))
    for name in "abc":
        iri = EX + name
        expected = backend.graph.query(_construct_node(f"FILTER (?s = <{iri}>)")).graph
        assert isomorphic(_as_graph(backend.resolve_iris([iri])[iri]), expected)


def test_an_unknown_prefix_still_fails_loudly():
    with pytest.raises(Exception, match="Unknown namespace prefix"):
        LocalSparqlBackend().resolve_iris(["foo:a"])


def test_resolving_a_missing_iri_gives_none():
    backend = _backend(_doc("a"))
    assert backend.resolve_iris([EX + "missing"]) == {EX + "missing": None}
    assert backend.resolve_iris(["ex:missing"]) == {"ex:missing": None}


def test_resolving_found_and_missing_iris_together():
    backend = _backend(_doc("a"))
    result = backend.resolve_iris([EX + "missing", EX + "a"])
    assert list(result) == [EX + "missing", EX + "a"]
    assert result[EX + "missing"] is None
    assert result[EX + "a"]["@id"] == EX + "a"


def test_storing_none_deletes_the_subject_only():
    backend = _backend(_doc("a", knows=["b"]), _doc("b"))
    assert backend.store_jsonld_dicts({EX + "a": None}).success
    assert (URIRef(EX + "a"), None, None) not in backend.graph
    assert backend.resolve_iris([EX + "a"]) == {EX + "a": None}
    assert backend.resolve_iris([EX + "b"])[EX + "b"]["@id"] == EX + "b"


def test_storing_none_for_an_unknown_subject_is_a_no_op():
    backend = _backend(_doc("a"))
    before = len(backend.graph)
    assert backend.store_jsonld_dicts({EX + "unknown": None}).success
    assert len(backend.graph) == before


def test_store_through_the_backend_interface_deletes_on_none():
    from oold.backend.interface import StoreParam

    backend = _backend(_doc("a"))
    backend.store(StoreParam(nodes={EX + "a": None}))
    assert len(backend.graph) == 0
