import importlib
import sys

import pytest

pytest.importorskip("psycopg")

from pydantic import ValidationError

from oold.backend.postgres import PostgresDocumentStore


@pytest.mark.parametrize("table", ["", "1abc", "a-b", 'x"; DROP TABLE y;--', "a" * 64])
def test_invalid_table_name_is_rejected_before_connecting(table):
    with pytest.raises(ValidationError):
        PostgresDocumentStore(dsn="postgresql://unused", table=table)


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
