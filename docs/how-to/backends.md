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

store = SqliteDocumentStore(db_path="./data/entities.db")  # or ":memory:"

set_resolver(SetResolverParam(iri="ex", resolver=store))
set_backend(SetBackendParam(iri="ex", backend=store))

# Same API as SimpleDictDocumentStore
store.store(StoreParam(nodes={"ex:alice": alice}))
alice = Person["ex:alice"]
```

---

## PostgresDocumentStore

Persists entities as JSONB rows in PostgreSQL, one row per IRI. It needs the `postgres` extra:

=== "uv (recommended)"

    ```bash
    uv add "oold[postgres]"
    ```

=== "pip"

    ```bash
    pip install "oold[postgres]"
    ```

```python
from oold.backend.postgres import PostgresDocumentStore

store = PostgresDocumentStore(dsn="postgresql://user:password@localhost:5432/mydb")

set_resolver(SetResolverParam(iri="ex", resolver=store))
set_backend(SetBackendParam(iri="ex", backend=store))

store.store(StoreParam(nodes={"ex:alice": alice}))
alice = Person["ex:alice"]

store.close()  # the connection stays open until you close it
```

- Entities live in table `entities` (`id TEXT PRIMARY KEY, data JSONB`), created on first use. Pass `table="..."` to use another name (letters, digits and underscores, up to 58 characters).
- Storing an IRI again overwrites its row, and a batch is written in one transaction.
- `index=True` (the default) adds a GIN index on `data` that serves equality conditions. Pass `index=False` to skip it.
- `query_limit=100` caps the rows a query returns. The default is no limit.
- Querying works as described in [Querying document stores](#querying-document-stores).

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

## Querying document stores

`SimpleDictDocumentStore` and `PostgresDocumentStore` answer the query DSL, so a condition on a model class subscripts straight into the store:

```python
Person[Person.age > 30]
Person[(Person.name == "Ada") & (Person.age >= 18)]
Person[(Person.name == "Ada") | (Person.name == "Bob")]
```

`==`, `!=`, `<`, `<=`, `>`, `>=`, `&` and `|` are supported. Put parentheses around each side of `&` and `|`.

### Nested fields

A field that embeds a model chains, so you can filter on what is inside it:

```python
from pydantic import BaseModel

class Address(BaseModel):
    city: str | None = None

class Person(LinkedBaseModel):
    id: str
    address: Address | None = None

Person[Person.address.city == "Berlin"]
```

The condition carries the dotted path `address.city`. You can also write it by hand with `Condition(field="address.city", ...)`. A document where the path is missing never matches, not even for `!=`.

Paths reach embedded objects only:

- A link is an IRI reference, not an embedded object. Compare it with an IRI (`Person.knows == "ex:bob"`). `Person.knows.name` raises, because following a link means looking up another document.
- A list of models cannot be indexed, so `Person.previous.city` raises.
- Chaining needs the default descriptor binding. With `OOLD_DESCRIPTOR_BINDING=0` it raises `NotImplementedError`.

### Differences between the stores

| | SimpleDictDocumentStore | PostgresDocumentStore |
| --- | --- | --- |
| A key that contains a dot | matches as a literal key first | always read as a path |
| A range on mixed types (`age < 36` on a string) | raises `TypeError` | does not match |
| Strings in a range | Python ordering | database collation |
| Result order | not defined | by IRI |

On PostgreSQL, equality is jsonb containment and uses the GIN index. Range conditions scan the table. A range only compares values of the same JSON type, so a JSON `null` or a string never matches `age < 36`.

---

## Querying a SPARQL backend

`SparqlResolver`, `LocalSparqlResolver` and `WikiDataSparqlResolver` translate
the query DSL into SPARQL, so `Model[Model.field == value]` reaches the store:

```python
from oold.backend.sparql import WikiDataSparqlResolver
from oold.backend.interface import SetResolverParam, set_resolver

set_resolver(SetResolverParam(iri="Item", resolver=WikiDataSparqlResolver()))
Person[Person.name == "Tim Berners-Lee"]
```

`eq`, `ne`, `lt`, `le`, `gt`, `ge` and `&` are supported. Anything else raises
rather than returning the wrong rows. That includes `|` and nested field paths
such as `Person.address.city`. The predicate and the literal are taken
from the model's own JSON-LD context, so a term scoped to a language produces a
language-tagged literal and one with an `@type` produces a typed one.

`WikiDataSparqlResolver` additionally constrains matches to the model's class -
a label matches more than one kind of thing.

!!! note "Public endpoints want a user agent"
    Wikidata answers the SPARQLWrapper default with
    `429 Aggressively rate-limiting to 1 req / min`, which looks like an outage
    rather than a policy. The resolvers send a descriptive `user_agent` by
    default; override it with your own tool name and contact URL.

## Multiple backends

Register different backends for different IRI prefixes:

```python
local_store  = SimpleDictDocumentStore()
remote_store = SqliteDocumentStore(db_path="remote.db")

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
