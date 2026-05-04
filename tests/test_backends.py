from typing import Optional

import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import (
    Backend,
    ResolveParam,
    SetBackendParam,
    SetResolverParam,
    StoreParam,
    set_backend,
    set_resolver,
)


def _store_procedure(store: Backend, pydantic_version="v2"):
    if pydantic_version == "v1":
        # based on pydantic v1
        from oold.model.v1 import LinkedBaseModel

        class Entity(LinkedBaseModel):
            class Config:
                schema_extra = {
                    "@context": {
                        # aliases
                        "id": "@id",
                        "type": "@type",
                        # prefixes
                        "ex": "https://example.com/",
                        # literal property
                        "name": "ex:name",
                    },
                    "$id": "https://example.com/Entity",  # the IRI of the schema
                }

            type: Optional[str] = "ex:Entity"
            name: str

            def get_iri(self):
                return "ex:" + self.name

    else:
        from pydantic import ConfigDict

        from oold.model import LinkedBaseModel

        class Entity(LinkedBaseModel):
            model_config = ConfigDict(
                json_schema_extra={
                    "@context": {
                        # aliases
                        "id": "@id",
                        "type": "@type",
                        # prefixes
                        "schema": "https://schema.org/",
                        "ex": "https://example.com/",
                        # literal property
                        "name": "schema:name",
                    },
                    "$id": "https://example.com/Entity",  # the IRI of the schema
                }
            )

            type: Optional[str] = "ex:Entity"
            name: str

            def get_iri(self):
                return "ex:" + self.name

    set_resolver(SetResolverParam(iri="ex", resolver=store))
    set_backend(SetBackendParam(iri="ex", backend=store))

    e = Entity(name="TestEntity")
    store.store(StoreParam(nodes={e.get_iri(): e}))

    e2 = store.resolve(ResolveParam(iris=[e.get_iri()], model_cls=Entity)).nodes[
        e.get_iri()
    ]
    assert e2.name == "TestEntity"

    e10 = Entity(name="AnotherEntity")
    e10.store_jsonld()
    e10_retrieved = Entity["ex:AnotherEntity"]
    assert e10_retrieved.name == "AnotherEntity"


def _run(store: Backend):
    _store_procedure(store, pydantic_version="v1")
    _store_procedure(store, pydantic_version="v2")


@pytest.mark.benchmark(group="backend")
def test_simple_dict_document_store(benchmark):
    store = SimpleDictDocumentStore()

    if benchmark is not None:
        benchmark(_run, store)
    else:
        _run(store)


@pytest.mark.benchmark(group="backend")
def test_sqlite_document_store(benchmark):
    from oold.backend.document_store import SqliteDocumentStore

    store = SqliteDocumentStore(db_path=":memory:")

    if benchmark is not None:
        benchmark(_run, store)
    else:
        _run(store)


@pytest.mark.benchmark(group="backend")
def test_local_sparql_store(benchmark):
    from oold.backend.sparql import LocalSparqlBackend

    store = LocalSparqlBackend()

    if benchmark is not None:
        benchmark(_run, store)
    else:
        _run(store)


def test_simple_dict_file_persistence(tmp_path):
    """Test SimpleDictDocumentStore with file_path for persistence."""
    from pydantic import ConfigDict

    from oold.model import LinkedBaseModel

    class Item(LinkedBaseModel):
        model_config = ConfigDict(
            json_schema_extra={
                "@context": {"ex": "https://example.com/", "name": "ex:name"},
                "$id": "https://example.com/Item",
            }
        )
        name: str

        def get_iri(self):
            return "ex:" + self.name

    file_path = tmp_path / "store.json"

    # Store
    store1 = SimpleDictDocumentStore(file_path=file_path)
    item = Item(name="Foo")
    store1.store(StoreParam(nodes={item.get_iri(): item}))
    assert file_path.exists()

    # Load in a new store instance
    store2 = SimpleDictDocumentStore(file_path=file_path)
    result = store2.resolve(ResolveParam(iris=["ex:Foo"], model_cls=Item))
    loaded = result.nodes["ex:Foo"]
    assert loaded.name == "Foo"


def test_simple_dict_file_no_file():
    """SimpleDictDocumentStore without file_path works in-memory only."""
    store = SimpleDictDocumentStore()
    assert store.file_path is None
    assert store._store == {}


if __name__ == "__main__":
    test_simple_dict_document_store(None)
    test_sqlite_document_store(None)
    test_local_sparql_store(None)
