# RDF Export

Every `LinkedBaseModel` instance can be serialized to JSON-LD via `to_jsonld()`. The resulting document carries the full semantic context defined in the model's `json_schema_extra`, making it directly importable into RDFLib, triple stores, or any JSON-LD consumer.

---

## Defining a model with semantic context

The `@context` block maps Python field names to RDF predicates. `$id` is the IRI of the class itself.

```python
from oold.model import LinkedBaseModel
from pydantic import ConfigDict
from typing import List, Optional

class Person(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "@context": {
                "id":    "@id",
                "type":  "@type",
                "schema": "https://schema.org/",
                "ex":    "https://example.com/",
                "name":  "schema:name",
                "knows": {"@id": "schema:knows", "@type": "@id"},
            },
            "$id": "https://example.com/Person",
        }
    )
    id: str
    name: str
    knows: List["Person"] = []
```

---

## Serializing to JSON-LD

```python
alice = Person(id="ex:alice", name="Alice")
bob   = Person(id="ex:bob",   name="Bob", knows=[alice])

print(bob.to_jsonld())
```

```json
{
  "@context": {
    "id": "@id",
    "type": "@type",
    "schema": "https://schema.org/",
    "ex": "https://example.com/",
    "name": "schema:name",
    "knows": {"@id": "schema:knows", "@type": "@id"}
  },
  "@id": "ex:bob",
  "@type": "https://example.com/Person",
  "name": "Bob",
  "knows": ["ex:alice"]
}
```

!!! note
    Nested object references are serialized as IRIs, not as embedded documents. This keeps the JSON-LD graph flat and avoids duplication across documents.

---

## Loading into RDFLib

```python
from rdflib import Graph

g = Graph()
g.parse(data=alice.to_jsonld(), format="json-ld")
g.parse(data=bob.to_jsonld(),   format="json-ld")

print(f"Graph has {len(g)} triples")
```

---

## Querying with SPARQL

```python
qres = g.query("""
    PREFIX schema: <https://schema.org/>

    SELECT ?name
    WHERE {
        ?person schema:knows ?other .
        ?other  schema:name  ?name .
    }
""")

for row in qres:
    print("Bob knows", row.name)
# Bob knows Alice
```

---

## Using LocalSparqlBackend for combined store + query

`LocalSparqlBackend` maintains an in-memory RDF graph. Store entities there and query them via SPARQL without leaving Python:

```python
from oold.backend.sparql import LocalSparqlBackend
from oold.backend.interface import SetResolverParam, SetBackendParam, StoreParam, set_resolver, set_backend

sparql = LocalSparqlBackend()
set_resolver(SetResolverParam(iri="ex", resolver=sparql))
set_backend(SetBackendParam(iri="ex", backend=sparql))

sparql.store(StoreParam(nodes={"ex:alice": alice, "ex:bob": bob}))

# Direct SPARQL on the internal graph
results = sparql.graph.query("""
    PREFIX schema: <https://schema.org/>
    SELECT ?s ?name WHERE { ?s schema:name ?name }
""")
for row in results:
    print(row.name)
```

---

## Round-trip: JSON-LD → model instance

You can reconstruct a model instance from its JSON-LD representation:

```python
import json
from oold.model import LinkedBaseModel

jsonld_str = alice.to_jsonld()
data = json.loads(jsonld_str)

# Re-hydrate (context is embedded, @id maps to id, @type maps to type)
alice2 = Person(id=data["@id"], name=data["name"])
print(alice2.name)  # Alice
```

For more complex round-trips — including nested objects — use a registered backend and resolve by IRI after storing.
