import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import ComparisonOperator, Condition, Query, field_path


def _eq(field, value):
    return Condition(field=field, operator=ComparisonOperator.EQ, value=value)


@pytest.mark.parametrize(
    ("field", "expected"),
    [("name", ["name"]), ("address.city", ["address", "city"]), ("a.b.c", ["a", "b", "c"])],
)
def test_field_path_splits_on_dots(field, expected):
    assert field_path(field) == expected


@pytest.mark.parametrize("field", ["", ".a", "a.", "a..b"])
def test_field_path_rejects_empty_segments(field):
    with pytest.raises(ValueError, match="empty segment"):
        field_path(field)


def test_or_builds_an_or_query():
    a, b = _eq("a", 1), _eq("b", 2)

    query = a | b

    assert isinstance(query, Query)
    assert query.operator == "or"
    assert query.op1 is a
    assert query.op2 is b


def test_or_combines_with_and_and_nested_queries():
    a, b, c = _eq("a", 1), _eq("b", 2), _eq("c", 3)

    query = (a & b) | c

    assert query.operator == "or"
    assert isinstance(query.op1, Query)
    assert query.op1.operator == "and"
    assert query.op2 is c
    assert (c | (a & b)).operator == "or"


def test_or_is_evaluated_by_the_document_store():
    store = SimpleDictDocumentStore()
    store.store_json_dicts({"ex:1": {"a": 1, "b": 0}, "ex:2": {"a": 0, "b": 2}, "ex:3": {"a": 0, "b": 0}})

    assert store._query(_eq("a", 1) | _eq("b", 2)) == {"ex:1", "ex:2"}
    assert store._query((_eq("a", 1) | _eq("b", 2)) & _eq("b", 2)) == {"ex:2"}
