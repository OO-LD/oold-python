"""RDF export, store and import scenarios, plus rdflib-only floors.

A scenario's ``prepare`` builds everything outside the measured window and
returns the callable to measure. ``verify`` checks the result afterwards, so a
fast but wrong run cannot pass.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from rdflib import Graph

from .dataset import NAMESPACE, build_person_model, make_people


@dataclass
class Prepared:
    run: Callable[[], None]
    verify: Callable[[], None]
    samples: list[float] = field(default_factory=list)


def _iri(person) -> str:
    return NAMESPACE + person.name


def _export_all(people) -> dict[str, dict]:
    return {_iri(person): person.to_jsonld() for person in people}


def _timed(samples: list[float], fn, *args):
    started = time.perf_counter()
    result = fn(*args)
    samples.append(time.perf_counter() - started)
    return result


def _stored_backend(docs: dict[str, dict]):
    from oold.backend.sparql import LocalSparqlBackend

    backend = LocalSparqlBackend()
    backend.store_jsonld_dicts(docs)
    return backend


def _count_triples(docs: dict[str, dict]) -> int:
    graph = Graph()
    for doc in docs.values():
        graph.parse(data=doc, format="json-ld")
    return len(graph)


def export(triples: int) -> Prepared:
    """Models to expanded JSON-LD, one ``to_jsonld`` per person."""
    people = make_people(build_person_model(), triples)
    docs: dict[str, dict] = {}
    samples: list[float] = []

    def run():
        for person in people:
            docs[_iri(person)] = _timed(samples, person.to_jsonld)

    def verify():
        assert len(docs) == len(people)
        assert _count_triples(docs) == triples

    return Prepared(run, verify, samples)


def store(triples: int) -> Prepared:
    """JSON-LD into ``LocalSparqlBackend``, one call per IRI."""
    from oold.backend.sparql import LocalSparqlBackend

    docs = _export_all(make_people(build_person_model(), triples))
    backend = LocalSparqlBackend()
    samples: list[float] = []

    def run():
        for iri, doc in docs.items():
            _timed(samples, backend.store_jsonld_dicts, {iri: doc})

    def verify():
        assert len(backend.graph) == triples

    return Prepared(run, verify, samples)


def import_(triples: int) -> Prepared:
    """Resolve every IRI from the backend back into models, one query per IRI."""
    from oold.backend.interface import ResolveParam

    person_cls = build_person_model()
    people = make_people(person_cls, triples)
    backend = _stored_backend(_export_all(people))
    nodes: dict = {}
    samples: list[float] = []

    def run():
        for person in people:
            iri = _iri(person)
            result = _timed(samples, backend.resolve, ResolveParam(iris=[iri], model_cls=person_cls))
            nodes.update(result.nodes)

    def verify():
        assert len(nodes) == len(people)
        for person in people:
            expected = person.model_dump()
            node = nodes[_iri(person)].model_dump()
            assert node["name"] == expected["name"]
            assert sorted(node["knows"]) == sorted(expected["knows"])

    return Prepared(run, verify, samples)


def rdflib_parse(triples: int) -> Prepared:
    """Floor for store: the same JSON-LD parsed into a plain rdflib graph."""
    docs = _export_all(make_people(build_person_model(), triples))
    graph = Graph()
    samples: list[float] = []

    def run():
        for doc in docs.values():
            _timed(samples, lambda doc=doc: graph.parse(data=doc, format="json-ld"))

    def verify():
        assert len(graph) == triples

    return Prepared(run, verify, samples)


def rdflib_serialize(triples: int) -> Prepared:
    """Floor for import: the whole graph serialized once instead of one query per IRI."""
    people = make_people(build_person_model(), triples)
    graph = _stored_backend(_export_all(people)).graph
    out: list[str] = []

    def run():
        out.append(graph.serialize(format="json-ld"))

    def verify():
        assert out
        assert len(json.loads(out[0])) == len(people)

    return Prepared(run, verify)


SCENARIOS: dict[str, Callable[[int], Prepared]] = {
    "export": export,
    "store": store,
    "import": import_,
    "rdflib_parse": rdflib_parse,
    "rdflib_serialize": rdflib_serialize,
}
