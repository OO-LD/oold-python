# Backends

Backends are the persistence and resolution layer for IRI-referenced entities. You register a backend for an IRI prefix, and all resolution and storage calls for that prefix are routed to it.

---

## The backend interface

Every backend implements two operations from `oold.backend.interface.Backend`:

- **`resolve_iris`** - fetch entities by IRI and deserialize them into model instances
- **`store_json_dicts`** - persist entities as JSON dictionaries

You configure which backend handles which IRI prefix using `set_resolver` and `set_backend`:

```python
from oold.backend.interface import SetResolverParam, SetBackendParam, set_resolver, set_backend

set_resolver(SetResolverParam(iri="ex", resolver=my_backend))  # routes reads for "ex:*"
set_backend(SetBackendParam(iri="ex", backend=my_backend))     # routes writes for "ex:*"
```

---

## SimpleDictDocumentStore

An in-memory dictionary store. Optionally persists to a JSON file.

```python
from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import (
    SetResolverParam, SetBackendParam, StoreParam,
    set_resolver, set_backend,
)

# In-memory only
store = SimpleDictDocumentStore()

# With JSON file persistence
store = SimpleDictDocumentStore(file_path="./data/entities.json")

set_resolver(SetResolverParam(iri="ex", resolver=store))
set_backend(SetBackendParam(iri="ex", backend=store))
```

### Storing entities

```python
from oold.backend.interface import StoreParam

store.store(StoreParam(nodes={
    "ex:alice": alice,
    "ex:bob":   bob,
}))
```

### Resolving entities

```python
from oold.backend.interface import ResolveParam

result = store.resolve(ResolveParam(iris=["ex:alice"], model_cls=Person))
alice_loaded = result.nodes["ex:alice"]
print(alice_loaded.name)  # Alice
```

### Shorthand via class subscript

Once a resolver is registered, use the class-level `[]` operator:

```python
alice = Person["ex:alice"]
```

### Storing via the model instance

```python
alice.store_jsonld()   # stores using the registered backend for the instance's IRI prefix
```

---

## SqliteDocumentStore

Persists entities in a SQLite database. Drop-in replacement for `SimpleDictDocumentStore`.

```python
from oold.backend.document_store import SqliteDocumentStore

store = SqliteDocumentStore(file_path="./data/entities.db")

set_resolver(SetResolverParam(iri="ex", resolver=store))
set_backend(SetBackendParam(iri="ex", backend=store))

# Same API as SimpleDictDocumentStore
store.store(StoreParam(nodes={"ex:alice": alice}))
alice = Person["ex:alice"]
```

---

## LocalSparqlBackend

An in-memory RDF graph (via [rdflib](https://rdflib.readthedocs.io/)) that supports SPARQL queries.

```python
from oold.backend.sparql import LocalSparqlBackend
from oold.backend.interface import SetResolverParam, SetBackendParam, set_resolver, set_backend

sparql_store = LocalSparqlBackend()
set_resolver(SetResolverParam(iri="ex", resolver=sparql_store))
set_backend(SetBackendParam(iri="ex", backend=sparql_store))

# Store and retrieve
sparql_store.store(StoreParam(nodes={"ex:alice": alice}))
alice_loaded = Person["ex:alice"]
```

The backend serializes each entity to JSON-LD before inserting it into the RDF graph, so all semantic annotations are preserved. See [RDF Export](rdf-export.md) for how to run SPARQL queries directly.

---

## Multiple backends

Register different backends for different IRI prefixes:

```python
local_store  = SimpleDictDocumentStore()
remote_store = SqliteDocumentStore(file_path="remote.db")

set_resolver(SetResolverParam(iri="local",  resolver=local_store))
set_resolver(SetResolverParam(iri="remote", resolver=remote_store))
set_backend(SetBackendParam(iri="local",    backend=local_store))
set_backend(SetBackendParam(iri="remote",   backend=remote_store))

# "local:*" and "remote:*" IRIs are routed independently
local_obj  = MyModel(id="local:obj1",  ...)
remote_obj = MyModel(id="remote:obj2", ...)
```

---

## Implementing a custom backend

Subclass `Backend` and implement `resolve_iris` and `store_json_dicts`:

```python
from oold.backend.interface import Backend, ResolveParam, ResolveResult, StoreParam

class MyCustomBackend(Backend):

    def resolve_iris(self, param: ResolveParam) -> ResolveResult:
        nodes = {}
        for iri in param.iris:
            raw = self._fetch(iri)           # your fetch logic here
            if raw is not None:
                nodes[iri] = param.model_cls(**raw)
        return ResolveResult(nodes=nodes)

    def store_json_dicts(self, param: StoreParam) -> None:
        for iri, entity in param.nodes.items():
            self._persist(iri, entity.model_dump())  # your persistence logic here

backend = MyCustomBackend()
set_resolver(SetResolverParam(iri="custom", resolver=backend))
set_backend(SetBackendParam(iri="custom",   backend=backend))
```

!!! note
    `resolve_iris` receives a `model_cls` so the backend knows which class to instantiate. When the type is encoded in the JSON document itself (via the `type` array), the backend can also perform type-based dispatch.
