# Code Generation

oold-python includes a `Generator` that converts OO-LD / JSON Schema definitions into fully typed Pydantic dataclasses using [`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator) under the hood.

---

## Minimal single-schema example

```python
import importlib
import datamodel_code_generator
from pathlib import Path

from oold.generator import Generator
import oold.model.model as model

schemas = [
    {
        "id": "Item",
        "title": "Item",
        "type": "object",
        "properties": {
            "id":    {"type": "string"},
            "type":  {"type": "array", "items": {"type": "string"}, "default": ["Item"]},
            "label": {"type": "string"},
        },
    }
]

g = Generator()
g.generate(Generator.GenerateParams(
    json_schemas=schemas,
    main_schema="Item.json",
    output_model_type=datamodel_code_generator.DataModelType.PydanticV2BaseModel,
    output_model_path=Path("generated_model.py"),
))
importlib.reload(model)

item = model.Item(id="ex:item1", label="My first item")
print(item.model_dump())
# {'id': 'ex:item1', 'type': ['Item'], 'label': 'My first item'}
```

!!! note
    `importlib.reload(model)` is required after generation so Python picks up the newly written file.

---

## Multi-schema example with references

Schemas can reference each other via `$ref`. The generator resolves the dependency graph automatically.

```python
schemas = [
    {
        "id": "Tag",
        "title": "Tag",
        "type": "object",
        "properties": {
            "id":   {"type": "string"},
            "type": {"type": "array", "items": {"type": "string"}, "default": ["Tag"]},
            "name": {"type": "string"},
        },
    },
    {
        "id": "Article",
        "title": "Article",
        "type": "object",
        "required": ["id", "title"],
        "properties": {
            "id":    {"type": "string"},
            "type":  {"type": "array", "items": {"type": "string"}, "default": ["Article"]},
            "title": {"type": "string"},
            # 'range' marks this field as an IRI reference to a Tag
            "tag":   {"type": "string", "range": "Tag.json"},
            "tags":  {"type": "array", "items": {"type": "string", "range": "Tag.json"}},
        },
    },
]

g = Generator()
g.generate(Generator.GenerateParams(
    json_schemas=schemas,
    main_schema="Article.json",
    output_model_type=datamodel_code_generator.DataModelType.PydanticV2BaseModel,
    output_model_path=Path("generated_model.py"),
))
importlib.reload(model)
```

Fields annotated with `"range": "<Schema>.json"` become IRI-transparent references: you can assign either a full `Tag` instance or an IRI string.

```python
tag = model.Tag(id="ex:t1", name="python")
article = model.Article(id="ex:a1", title="Hello World", tag=tag)
# or by IRI — resolved lazily when accessed
article2 = model.Article(id="ex:a2", title="Another Post", tag="ex:t1")
```

---

## Schema inheritance with `allOf`

Use `allOf` to compose schemas:

```python
schemas = [
    {
        "id": "Base",
        "title": "Base",
        "type": "object",
        "properties": {
            "id":   {"type": "string"},
            "type": {"type": "array", "items": {"type": "string"}, "default": ["Base"]},
        },
    },
    {
        "id": "Extended",
        "title": "Extended",
        "type": "object",
        "allOf": [{"$ref": "Base.json"}],
        "properties": {
            "type":        {"type": "array", "items": {"type": "string"}, "default": ["Extended"]},
            "extra_field": {"type": "string"},
        },
    },
]
```

The generated `Extended` class inherits all fields from `Base`.

---

## Output model types

| Constant | Pydantic version | Use when |
|---|---|---|
| `PydanticV2BaseModel` | v2 (recommended) | new projects |
| `PydanticBaseModel` | v1 (legacy) | existing v1 codebases |

```python
import datamodel_code_generator

# Pydantic v2
output_model_type = datamodel_code_generator.DataModelType.PydanticV2BaseModel

# Pydantic v1 (legacy)
output_model_type = datamodel_code_generator.DataModelType.PydanticBaseModel
```

---

## Output path

`output_model_path` accepts any `pathlib.Path`. The generator writes a single `.py` file containing all generated classes.

```python
from pathlib import Path

Generator.GenerateParams(
    ...
    output_model_path=Path("src/mypackage/generated.py"),
)
```

Commit the generated file to version control so downstream code has stable imports and the generation step is only re-run when schemas change.
