from typing import Optional

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
                    "iri": "Entity.json",  # the IRI of the schema
                }

            type: Optional[str] = "ex:Entity.json"
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
                    "iri": "Entity.json",  # the IRI of the schema
                }
            )

            type: Optional[str] = "ex:Entity.json"
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


def test_simple_dict_document_store():
    store = SimpleDictDocumentStore()
    _run(store)


def test_sqlite_document_store():
    from oold.backend.document_store import SqliteDocumentStore

    store = SqliteDocumentStore(db_path=":memory:")

    _run(store)


def test_local_sparql_store():
    from oold.backend.sparql import LocalSparqlBackend

    store = LocalSparqlBackend()

    _run(store)


if __name__ == "__main__":
    # test_simple_dict_document_store()
    # test_sqlite_document_store()
    test_local_sparql_store()
