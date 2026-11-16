"""Translating the query DSL into SPARQL.

The DSL builds a ``Condition`` / ``Query`` from ``Model.field == value`` and
friends. Two things consume it: ``apply_operator``, which filters objects already
in memory, and the SPARQL resolvers, which have to ask a triple store the same
question. The check that matters is that they agree - so every case here asserts
the SPARQL answer against the in-memory one over the same data, rather than
against a hand-written expectation.

Runs against ``LocalSparqlResolver`` (an in-process rdflib graph), so no network.
"""

import pytest
from pydantic import BaseModel, ConfigDict
from rdflib import Graph

from oold.backend.interface import (
    ComparisonOperator,
    Condition,
    Query,
    QueryParam,
    SetResolverParam,
    apply_operator,
    set_resolver,
)
from oold.backend.sparql import LocalSparqlBackend, _translate
from oold.model._descriptor import LinkedBaseModel

EX = "https://sparqltest.example/"
XSD_INT = "http://www.w3.org/2001/XMLSchema#integer"


class Person(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                "id": "@id",
                "type": "@type",
                # full IRIs, no prefix: a prefix would make compaction rewrite
                # the ids too, and the comparison below is about the result set
                "name": {"@id": EX + "name"},
                "age": {"@id": EX + "age", "@type": XSD_INT},
            },
            "iri": EX + "Person",
        }
    )
    id: str
    type: str | None = EX + "Person"
    name: str | None = None
    age: int | None = None

    def get_iri(self):
        return self.id


# full IRIs, not prefixed: LocalSparqlBackend hardcodes a single "ex:" prologue
PEOPLE = [
    Person(id=EX + "alice", name="Alice", age=30),
    Person(id=EX + "bob", name="Bob", age=45),
    Person(id=EX + "carol", name="Carol", age=45),
]


@pytest.fixture
def backend():
    store = LocalSparqlBackend(graph=Graph())
    store.store_jsonld_dicts({p.get_iri(): p.to_jsonld() for p in PEOPLE})
    set_resolver(SetResolverParam(iri="https", resolver=store))
    return store


def _in_memory(condition) -> set[str]:
    """What apply_operator says, over the same objects."""

    def matches(person, node) -> bool:
        if isinstance(node, Query):
            assert node.operator == "and"
            return matches(person, node.op1) and matches(person, node.op2)
        return apply_operator(node.operator, getattr(person, node.field, None), node.value)

    return {p.id for p in PEOPLE if matches(p, condition)}


def _via_sparql(backend, condition) -> set[str]:
    result = backend.query(QueryParam(query=condition, model_cls=Person))
    return {node.id for node in result.nodes.values() if node is not None}


@pytest.mark.parametrize(
    "operator,field,value",
    [
        (ComparisonOperator.EQ, "name", "Bob"),
        (ComparisonOperator.NE, "name", "Bob"),
        (ComparisonOperator.EQ, "age", 45),
        (ComparisonOperator.LT, "age", 45),
        (ComparisonOperator.LE, "age", 45),
        (ComparisonOperator.GT, "age", 30),
        (ComparisonOperator.GE, "age", 30),
    ],
)
def test_sparql_agrees_with_the_in_memory_filter(backend, operator, field, value):
    condition = Condition(field=field, operator=operator, value=value)
    expected = _in_memory(condition)
    assert expected, "the fixture should exercise a non-empty result"
    assert _via_sparql(backend, condition) == expected


def test_conjunction(backend):
    condition = Query(
        op1=Condition(field="age", operator=ComparisonOperator.EQ, value=45),
        operator="and",
        op2=Condition(field="name", operator=ComparisonOperator.EQ, value="Bob"),
    )
    assert _via_sparql(backend, condition) == _in_memory(condition) == {EX + "bob"}


def test_the_model_context_decides_the_predicate_and_the_literal():
    """Not a second reading of the context - it is expanded, like the payload."""
    patterns = _translate(Condition(field="age", operator=ComparisonOperator.GT, value=40), Person, [0])
    assert f"<{EX}age>" in patterns
    assert f'"40"^^<{XSD_INT}>' in patterns


def test_an_untranslatable_operator_raises_rather_than_guessing(backend):
    condition = Query(
        op1=Condition(field="name", operator=ComparisonOperator.EQ, value="Bob"),
        operator="or",
        op2=Condition(field="name", operator=ComparisonOperator.EQ, value="Alice"),
    )
    with pytest.raises(NotImplementedError, match="or"):
        backend.query(QueryParam(query=condition, model_cls=Person))


def test_unmapped_field_raises(backend):
    with pytest.raises(ValueError, match="not mapped"):
        backend.query(
            QueryParam(
                query=Condition(field="nope", operator=ComparisonOperator.EQ, value="x"),
                model_cls=Person,
            )
        )


class Address(BaseModel):
    city: str | None = None


class Located(LinkedBaseModel):
    """A model whose context has a ``@vocab``: any unknown term expands to a predicate."""

    model_config = ConfigDict(
        json_schema_extra={
            "@context": {"id": "@id", "type": "@type", "@vocab": EX},
            "iri": EX + "Located",
        }
    )
    id: str
    type: str | None = EX + "Located"
    name: str | None = None
    address: Address | None = None


def test_a_nested_path_is_rejected_instead_of_becoming_a_made_up_predicate(backend):
    """Without the check, ``address.city`` expands against ``@vocab`` and quietly matches nothing."""
    condition = Located.address.city == "Berlin"

    with pytest.raises(NotImplementedError, match=r"address\.city"):
        _translate(condition, Located, [0])
    with pytest.raises(NotImplementedError, match=r"address\.city"):
        backend.query(QueryParam(query=condition, model_cls=Located))


def test_a_nested_path_inside_a_conjunction_is_rejected():
    condition = (Located.name == "x") & (Located.address.city == "Berlin")

    with pytest.raises(NotImplementedError, match=r"address\.city"):
        _translate(condition, Located, [0])


def test_a_dotted_term_that_is_not_a_nested_path_still_translates():
    """Only a dotted field whose head is an embedded model field is a nested path."""

    class Dotted(LinkedBaseModel):
        model_config = ConfigDict(
            json_schema_extra={
                "@context": {"id": "@id", "type": "@type", "a.b": {"@id": EX + "ab"}},
                "iri": EX + "Dotted",
            }
        )
        id: str
        type: str | None = EX + "Dotted"

    patterns = _translate(Condition(field="a.b", operator=ComparisonOperator.EQ, value="x"), Dotted, [0])

    assert f"<{EX}ab>" in patterns
