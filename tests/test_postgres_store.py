import importlib
import sys

import pytest

pytest.importorskip("psycopg")

from psycopg import sql
from pydantic import ValidationError

from oold.backend.interface import ComparisonOperator, Condition, Query, QueryParam
from oold.backend.postgres import PostgresDocumentStore, _where
from oold.model import LinkedBaseModel


class Row(LinkedBaseModel):
    id: str


def _eq(field, value):
    return Condition(field=field, operator=ComparisonOperator.EQ, value=value)


def _compare(field, operator, value):
    return Condition(field=field, operator=operator, value=value)


def _ids(store, condition) -> list[str]:
    statement, params = store._select(condition)
    return [row[0] for row in store._connection().execute(statement, params).fetchall()]


def _plan(store, condition) -> str:
    statement, params = store._select(condition)
    conn = store._connection()
    with conn.transaction():
        conn.execute("SET LOCAL enable_seqscan = off")
        rows = conn.execute(sql.SQL("EXPLAIN ") + statement, params).fetchall()
    return "\n".join(row[0] for row in rows)


def _index_names(store) -> set[str]:
    rows = store._connection().execute("SELECT indexname FROM pg_indexes WHERE tablename = %s", (store.table,))
    return {row[0] for row in rows}


@pytest.mark.parametrize("table", ["", "1abc", "a-b", 'x"; DROP TABLE y;--', "a" * 59, "a" * 64])
def test_invalid_table_name_is_rejected_before_connecting(table):
    with pytest.raises(ValidationError):
        PostgresDocumentStore(dsn="postgresql://unused", table=table)


def test_query_limit_must_be_positive():
    with pytest.raises(ValidationError):
        PostgresDocumentStore(dsn="postgresql://unused", query_limit=0)


def test_an_unknown_query_operator_is_rejected():
    with pytest.raises(NotImplementedError, match="xor"):
        _where(Query(op1=_eq("a", 1), operator="xor", op2=_eq("b", 2)))


def test_a_query_node_of_the_wrong_type_is_rejected():
    with pytest.raises(TypeError):
        _where("a == 1")  # type: ignore[arg-type]


def test_missing_driver_names_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)
    monkeypatch.delitem(sys.modules, "oold.backend.postgres")

    with pytest.raises(ImportError, match=r"oold\[postgres\]"):
        importlib.import_module("oold.backend.postgres")


@pytest.mark.postgres
def test_close_is_idempotent_and_the_store_reconnects(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"name": "one"}})
    postgres_store.close()
    postgres_store.close()

    assert postgres_store.resolve_iris(["ex:a"]) == {"ex:a": {"name": "one"}}


@pytest.mark.postgres
def test_store_overwrites_existing_iri(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"name": "one"}})
    postgres_store.store_json_dicts({"ex:a": {"name": "two"}})

    assert postgres_store.resolve_iris(["ex:a"]) == {"ex:a": {"name": "two"}}


@pytest.mark.postgres
def test_resolve_skips_unknown_iris(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"name": "one"}})

    assert postgres_store.resolve_iris(["ex:a", "ex:missing"]) == {"ex:a": {"name": "one"}}
    assert postgres_store.resolve_iris([]) == {}


@pytest.mark.postgres
def test_nested_json_roundtrips(postgres_store):
    doc = {
        "name": "Zoë",
        "tags": ["a", "b"],
        "nested": {"n": 1, "f": 1.5, "flag": True, "none": None, "list": [{"k": "v"}]},
    }
    postgres_store.store_json_dicts({"ex:doc": doc})

    assert postgres_store.resolve_iris(["ex:doc"]) == {"ex:doc": doc}


@pytest.mark.postgres
def test_data_persists_across_instances(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"name": "one"}})
    postgres_store.close()

    reopened = PostgresDocumentStore(dsn=postgres_store.dsn, table=postgres_store.table)
    try:
        assert reopened.resolve_iris(["ex:a"]) == {"ex:a": {"name": "one"}}
    finally:
        reopened.close()


@pytest.mark.postgres
def test_range_conditions_only_compare_values_of_the_same_json_type(postgres_store):
    postgres_store.store_json_dicts({
        "ex:num": {"age": 10},
        "ex:null": {"age": None},
        "ex:str": {"age": "abc"},
        "ex:none": {},
    })

    assert _ids(postgres_store, _compare("age", ComparisonOperator.LT, 36)) == ["ex:num"]
    assert _ids(postgres_store, _compare("age", ComparisonOperator.GE, 5)) == ["ex:num"]
    assert _ids(postgres_store, _compare("age", ComparisonOperator.GT, "abb")) == ["ex:str"]


@pytest.mark.postgres
def test_not_equal_matches_other_types_but_never_a_missing_path(postgres_store):
    postgres_store.store_json_dicts({"ex:num": {"age": 10}, "ex:str": {"age": "abc"}, "ex:none": {}})

    assert _ids(postgres_store, _compare("age", ComparisonOperator.NE, 10)) == ["ex:str"]


@pytest.mark.postgres
def test_equality_on_a_nested_list_does_not_match_an_item(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"x": {"tags": ["a", "b"]}}, "ex:b": {"x": {"tags": "a"}}})

    assert _ids(postgres_store, _eq("x.tags", "a")) == ["ex:b"]


@pytest.mark.postgres
def test_equality_between_numbers_ignores_the_representation(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"n": 1}, "ex:b": {"n": 1.5}})

    assert _ids(postgres_store, _eq("n", 1.0)) == ["ex:a"]


@pytest.mark.postgres
def test_a_condition_without_an_operator_means_equality(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"name": "Ada"}, "ex:b": {"name": "Bob"}})

    assert _ids(postgres_store, Condition(field="name", value="Ada")) == ["ex:a"]


@pytest.mark.postgres
def test_results_are_ordered_by_iri_and_cut_at_the_query_limit(postgres_store, make_postgres_store):
    postgres_store.store_json_dicts({"ex:c": {"k": 1}, "ex:a": {"k": 1}, "ex:b": {"k": 1}})
    limited = make_postgres_store(table=postgres_store.table, query_limit=2)

    assert _ids(postgres_store, _eq("k", 1)) == ["ex:a", "ex:b", "ex:c"]
    assert _ids(limited, _eq("k", 1)) == ["ex:a", "ex:b"]


@pytest.mark.postgres
def test_query_needs_a_model_class(postgres_store):
    with pytest.raises(ValueError, match="model_cls"):
        postgres_store.query(QueryParam(query=_eq("name", "Ada")))


@pytest.mark.postgres
def test_query_returns_resolved_nodes(postgres_store):
    postgres_store.store_json_dicts({"ex:a": {"id": "ex:a", "n": 1}, "ex:b": {"id": "ex:b", "n": 2}})

    result = postgres_store.query(QueryParam(query=_eq("n", 2), model_cls=Row))

    assert list(result.nodes) == ["ex:b"]
    assert result.nodes["ex:b"].id == "ex:b"


@pytest.mark.postgres
def test_hostile_field_names_and_values_are_plain_data(postgres_store):
    hostile_field = "x'); DROP TABLE entities;--"
    postgres_store.store_json_dicts({"ex:a": {"name": "O'Brien", hostile_field: "yes"}})

    assert _ids(postgres_store, _eq("name", "O'Brien")) == ["ex:a"]
    assert _ids(postgres_store, _eq("name", "x' OR '1'='1")) == []
    assert _ids(postgres_store, _eq(hostile_field, "yes")) == ["ex:a"]
    assert postgres_store.resolve_iris(["ex:a"])  # the table survived


@pytest.mark.postgres
def test_equality_uses_the_gin_index_and_ranges_scan(postgres_store):
    index = f"{postgres_store.table}_gin"

    assert index in _plan(postgres_store, _eq("address.city", "Berlin"))
    assert index not in _plan(postgres_store, _compare("age", ComparisonOperator.GT, 36))


@pytest.mark.postgres
def test_the_index_can_be_turned_off(postgres_store, make_postgres_store):
    plain = make_postgres_store(index=False)

    assert f"{postgres_store.table}_gin" in _index_names(postgres_store)
    assert _index_names(plain) == {f"{plain.table}_pkey"}


@pytest.mark.postgres
def test_the_longest_table_name_still_fits_its_index_name(make_postgres_store):
    store = make_postgres_store(table="t" * 58)

    assert f"{'t' * 58}_gin" in _index_names(store)
