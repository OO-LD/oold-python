"""One query contract for every store that implements ``query``.

Conditions come from the DSL, so chaining and the store are exercised together.
Every store must answer the same, including for documents that lack the path:
a missing path never matches, not even for ``!=``.
"""

import pytest
from pydantic import BaseModel

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import ComparisonOperator, Condition, QueryParam
from oold.model import LinkedBaseModel


class Geo(BaseModel):
    lat: float | None = None


class Address(BaseModel):
    city: str | None = None
    geo: Geo | None = None


class Person(LinkedBaseModel):
    id: str
    type: str | None = "qstore:Person"
    name: str | None = None
    age: int | None = None
    address: Address | None = None


DOCS = {
    "ex:ada": {
        "id": "ex:ada",
        "type": "qstore:Person",
        "name": "Ada",
        "age": 36,
        "address": {"city": "Berlin", "geo": {"lat": 52.5}},
    },
    "ex:bob": {
        "id": "ex:bob",
        "type": "qstore:Person",
        "name": "Bob",
        "age": 41,
        "address": {"city": "Paris", "geo": {"lat": 48.9}},
    },
    "ex:cy": {"id": "ex:cy", "type": "qstore:Person", "name": "Cy", "age": 29},
    "ex:dee": {
        "id": "ex:dee",
        "type": "qstore:Person",
        "name": "Dee",
        "age": 41,
        "address": {"city": "Berlin"},
    },
}


@pytest.fixture(params=["dict"])
def query_store(request):
    store = SimpleDictDocumentStore()
    store.store_json_dicts(DOCS)
    yield store


def _matches(store, condition) -> set[str]:
    return set(store.query(QueryParam(query=condition, model_cls=Person)).nodes)


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (lambda: Person.name == "Ada", {"ex:ada"}),
        (lambda: Person.age != 41, {"ex:ada", "ex:cy"}),
        (lambda: Person.age < 36, {"ex:cy"}),
        (lambda: Person.age <= 36, {"ex:ada", "ex:cy"}),
        (lambda: Person.age > 36, {"ex:bob", "ex:dee"}),
        (lambda: Person.age >= 41, {"ex:bob", "ex:dee"}),
        (lambda: (Person.name == "Bob") & (Person.age == 41), {"ex:bob"}),
        (lambda: (Person.name == "Ada") | (Person.name == "Cy"), {"ex:ada", "ex:cy"}),
        (lambda: Person.name == "Nobody", set()),
    ],
    ids=["eq", "ne", "lt", "le", "gt", "ge", "and", "or", "no-match"],
)
def test_top_level_conditions(query_store, build, expected):
    assert _matches(query_store, build()) == expected


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (lambda: Person.address.city == "Berlin", {"ex:ada", "ex:dee"}),
        (lambda: Person.address.geo.lat > 50, {"ex:ada"}),
        (lambda: Person.address.geo.lat <= 52.5, {"ex:ada", "ex:bob"}),
        # a missing path never matches, also not for !=
        (lambda: Person.address.city != "Berlin", {"ex:bob"}),
        (lambda: Person.address.geo.lat == 99, set()),
        (lambda: (Person.address.city == "Berlin") & (Person.age > 36), {"ex:dee"}),
        (lambda: (Person.address.city == "Paris") | (Person.address.geo.lat > 52), {"ex:ada", "ex:bob"}),
        (lambda: (Person.address.city == "Berlin") & (Person.age == 41) | (Person.name == "Cy"), {"ex:dee", "ex:cy"}),
    ],
    ids=["eq", "deeper", "le", "ne-skips-missing", "no-match", "and", "or", "and-or"],
)
def test_nested_path_conditions(query_store, build, expected):
    assert _matches(query_store, build()) == expected


def test_a_path_into_a_scalar_does_not_match(query_store):
    condition = Condition(field="name.first", operator=ComparisonOperator.EQ, value="Ada")

    assert _matches(query_store, condition) == set()


@pytest.mark.parametrize("field", ["address..city", ".address", "address."])
def test_a_malformed_path_is_rejected(query_store, field):
    condition = Condition(field=field, operator=ComparisonOperator.EQ, value="Berlin")

    with pytest.raises(ValueError, match="empty segment"):
        _matches(query_store, condition)


def test_a_dotted_literal_key_still_matches_in_the_dict_store():
    store = SimpleDictDocumentStore()
    store.store_json_dicts({"ex:lit": {"id": "ex:lit", "http://example.org/p": "x"}})

    assert store._query(Condition(field="http://example.org/p", operator=ComparisonOperator.EQ, value="x")) == {
        "ex:lit"
    }


def test_a_document_that_is_none_never_matches():
    store = SimpleDictDocumentStore()
    store.store_json_dicts({"ex:gone": None})

    assert store._query(Condition(field="name", operator=ComparisonOperator.EQ, value="x")) == set()
