# Object Graph Mapping

oold-python's core feature is *IRI-transparent references*: a field annotated with `range` can hold either a Python object or an IRI string. The library resolves IRIs on first access via the registered backend.

---

## Direct object assignment

The simplest case — pass objects directly:

```python
from oold.model import LinkedBaseModel
from pydantic import ConfigDict
from typing import List, Optional

class Tag(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.com/Tag"})
    id: str
    name: str

class Article(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.com/Article"})
    id: str
    title: str
    primary_tag: Optional[Tag] = None
    tags: List[Tag] = []

python_tag  = Tag(id="ex:tag-python",  name="python")
async_tag   = Tag(id="ex:tag-async",   name="async")

article = Article(
    id="ex:article-1",
    title="Async Python Tips",
    primary_tag=python_tag,
    tags=[python_tag, async_tag],
)

print(article.primary_tag.name)   # python
print(article.tags[1].name)       # async
```

---

## IRI string assignment and lazy resolution

Assign IRI strings instead of objects. The backend resolves them on first access.

```python
from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, StoreParam, set_resolver

store = SimpleDictDocumentStore()
set_resolver(SetResolverParam(iri="ex", resolver=store))

# Pre-populate the backend
store.store(StoreParam(nodes={
    "ex:tag-python": python_tag,
    "ex:tag-async":  async_tag,
}))

# Assign IRIs — objects are NOT loaded yet
article2 = Article(
    id="ex:article-2",
    title="Another Post",
    primary_tag="ex:tag-python",   # IRI string
    tags=["ex:tag-python", "ex:tag-async"],
)

# First access triggers backend resolution
print(article2.primary_tag.name)  # python  — loaded from store on demand
print(article2.tags[0].name)      # python
```

!!! tip
    Lazy resolution keeps startup fast: only the entities you actually access are fetched from the backend.

---

## Resolving by IRI directly

Use the class-level `[]` operator as a shorthand:

```python
tag = Tag["ex:tag-python"]   # equivalent to store.resolve(...)
print(tag.name)              # python
```

---

## Mixing objects and IRIs

You can mix concrete objects and IRIs in a list:

```python
article3 = Article(
    id="ex:article-3",
    title="Mixed References",
    tags=[python_tag, "ex:tag-async"],  # one object, one IRI
)
```

---

## `cast()` — converting between model classes

`cast()` converts an instance from one model class to another while preserving `__iris__` references.

```python
from oold.model import LinkedBaseModel

class ArticleV1(LinkedBaseModel):
    id: str
    title: str
    body: str = ""

class ArticleV2(LinkedBaseModel):
    id: str
    title: str
    content: str = ""   # renamed field

v1 = ArticleV1(id="ex:a1", title="Hello", body="Some text")

# Cast to V2; fields not on V2 are dropped, None fields use V2 defaults
v2 = v1.cast(ArticleV2, remove_extra=True, none_to_default=True)
print(v2.id)       # ex:a1
print(v2.title)    # Hello
print(v2.content)  # ""  — default, since 'body' doesn't exist on V2
```

`cast()` parameters:

| Parameter | Effect |
|---|---|
| `remove_extra=True` | Drop fields not defined on the target class |
| `none_to_default=True` | Replace `None` / empty-list values with the target's defaults |
| `silent=True` | Suppress warnings about dropped fields (default) |

You can also construct a target instance directly from another model:

```python
v2 = ArticleV2(v1, content="migrated")
```

---

## Default IRI values

A field can carry a default IRI that is resolved automatically on instantiation:

```python
# Schema definition
{
    "b_default": {"type": "string", "range": "Tag.json", "default": "ex:tag-python"}
}
```

When you instantiate the model without supplying `b_default`, the IRI `"ex:tag-python"` is used and resolved on first access.
