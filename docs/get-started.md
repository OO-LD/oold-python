# Get Started

This guide walks you from a fresh install to a working end-to-end example.

## Prerequisites

- Python **3.10 or later**
- `pip` or [`uv`](https://docs.astral.sh/uv/) (recommended)

## Installation

=== "uv (recommended)"

    ```bash
    uv add oold
    ```

=== "pip"

    ```bash
    pip install oold
    ```

Verify the installation:

```bash
python -c "import oold; print(oold.__version__)"
```

---

## Hello World

The following example covers the full core workflow in one script:

1. Define a JSON Schema
2. Generate a typed Pydantic model
3. Populate a backend
4. Resolve objects by IRI
5. Serialize to JSON-LD

```python
import importlib
import datamodel_code_generator
from pathlib import Path
from pydantic import ConfigDict

from oold.generator import Generator
from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, SetBackendParam, StoreParam, set_resolver, set_backend
import oold.model.model as model

# 1. Define schemas
schemas = [
    {
        "id": "Person",
        "title": "Person",
        "type": "object",
        "properties": {
            "id":   {"type": "string"},
            "type": {"type": "array", "items": {"type": "string"}, "default": ["Person"]},
            "name": {"type": "string"},
        },
    },
]

# 2. Generate the Pydantic model into a file, then reload
output_path = Path("generated_model.py")
g = Generator()
g.generate(Generator.GenerateParams(
    json_schemas=schemas,
    main_schema="Person.json",
    output_model_type=datamodel_code_generator.DataModelType.PydanticV2BaseModel,
    output_model_path=output_path,
))
importlib.reload(model)  # pick up the freshly written module

# 3. Create instances and a backend
store = SimpleDictDocumentStore()
set_resolver(SetResolverParam(iri="ex", resolver=store))
set_backend(SetBackendParam(iri="ex", backend=store))

alice = model.Person(id="ex:alice", name="Alice")
bob   = model.Person(id="ex:bob",   name="Bob")

store.store(StoreParam(nodes={"ex:alice": alice, "ex:bob": bob}))

# 4. Resolve by IRI
loaded = model.Person["ex:alice"]
print(loaded.name)   # Alice

# 5. Serialize to JSON-LD
print(alice.to_jsonld())
```

```json
{
  "@id": "ex:alice",
  "@type": ["Person"],
  "name": "Alice"
}
```

---

## What's next?

| Topic | Guide |
|---|---|
| Generate models from complex schemas | [Code Generation](how-to/codegen.md) |
| Work with IRI references and lazy resolution | [Object Graph Mapping](how-to/object-graph-mapping.md) |
| Persist and query with different backends | [Backends](how-to/backends.md) |
| Export to RDF and run SPARQL queries | [RDF Export](how-to/rdf-export.md) |
| Separate runtime state from data | [BaseController](how-to/controller.md) |
