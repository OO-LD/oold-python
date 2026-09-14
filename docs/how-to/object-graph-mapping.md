# Object Graph Mapping

oold-python's core feature is *IRI-transparent references*: a link field can hold either a Python object or an IRI string. The library resolves IRIs on first access via the registered backend.

## Recommended declaration

Declare a link with `Link[T]` or `LinkList[T]` and `OoldField(range=...)`:

```python
from oold.model import Link, LinkedBaseModel, LinkList, OoldField

class Person(LinkedBaseModel):
    id: str
    name: str | None = None
    employer: Link["Organization | None"] = OoldField(range="Organization.json")
    knows: LinkList["Person"] = OoldField(range="Person.json")
```

This is the only form that gives a type checker **both** of a link's types - the
resolved object you read and the object, IRI or JSON object you may write - and
the only one where optionality is stated rather than assumed. `range=` keeps the
schema self-describing. [Typed link declarations](#typed-link-declarations)
explains why; the other notations, and what each one gives up, are tabulated in
[the design doc](../design/graph-object-binding.md#which-notation-supports-what).

Older declarations keep working unchanged, including the legacy
`Optional[List[Bar]] = Field(None, json_schema_extra={"range": "Bar.json"})`
that code generation still emits. Nothing below needs rewriting; the
recommendation applies to code you write now.

---

## Direct object assignment

The simplest case - pass objects directly:

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

# Assign IRIs - objects are NOT loaded yet
article2 = Article(
    id="ex:article-2",
    title="Another Post",
    primary_tag="ex:tag-python",   # IRI string
    tags=["ex:tag-python", "ex:tag-async"],
)

# First access triggers backend resolution
print(article2.primary_tag.name)  # python  - loaded from store on demand
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

## `cast()` - converting between model classes

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
print(v2.content)  # ""  - default, since 'body' doesn't exist on V2
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

---

## Typed link declarations

The declaration above works, but a type checker only sees half of it. A link has
**two** types: reading it yields a resolved object, while writing it accepts that
object *or* a reference to it - an IRI string, or a JSON object still to be
constructed. A single annotation can only state one, so `knows: list[Person]`
rejects `knows=["ex:bob"]` even though the library accepts it at runtime.

`Link[T]` and `LinkList[T]` carry both. They are exported from `oold.model`:

```python
from oold.model import Link, LinkedBaseModel, LinkList, OoldField

class Person(LinkedBaseModel):
    id: str
    name: str | None = None
    employer: Link["Organization | None"] = OoldField(range="Organization.json")
    knows: LinkList["Person | None"] = OoldField(range="Person.json")

# accepted: an object, an IRI, or a JSON object
alice = Person(id="ex:alice", knows=["ex:bob", {"id": "ex:carol"}])
alice.knows[0]        # a Person, not a str
```

Nothing changes at runtime - same resolution, same JSON Schema. Only what the
checker sees changes.

### Optionality is declared

`Link[T]` reads as `T`, so a chain needs no guard at every hop. `Link[T | None]`
reads as `T | None`, because absence is then part of the model:

```python
class Person(LinkedBaseModel):
    father: Link["Person"] = OoldField()          # promises a Person
    mother: Link["Person | None"] = OoldField()   # may legitimately be absent

person.father.father.father.name    # no guards
```

A link declared mandatory raises `LinkNotResolved` when it is unset or when the
backend cannot place the reference, so one `try/except` covers a whole walk:

```python
from oold.model import LinkNotResolved

try:
    while True:
        person = person.father
        print(person.name)
except LinkNotResolved:
    print("ancestry ends here")
```

A **transport failure is not absence** - a connection error propagates unchanged
rather than being reported as a missing link.

### `OoldField` arguments

All keyword-only, all optional:

```python
OoldField(range=None, link=None, required_iri=None, **field_kwargs)
```

| argument | effect |
|---|---|
| `range` | target schema IRI, emitted as `x-oold-range`. Omitted, the target is inferred from the annotation and the schema declares no range |
| `link` | force link treatment where the annotation does not imply it, as in a union arm. Redundant with `Link[T]` / `LinkList[T]` |
| `required_iri` | emitted as `x-oold-required-iri`: the reference must carry an IRI, so an inline object without one is rejected. Not the same as optionality, which the annotation declares |
| `**field_kwargs` | passed to `pydantic.Field` (`alias`, `description`, `default_factory`, ...). `default=None` is supplied unless you pass a `default_factory` |

!!! note "Write the whole annotation"
    Spell the union inside: `Link[T | None]`, not `Optional[Link[T]]`, and
    `LinkList[T]`, not `list[Link[T]]`. Nested in another annotation a checker
    stops applying descriptor rules - `list[Link[T]]` reads as a list of
    descriptors, and `Optional[Link[T]]` narrows on read but rejects an IRI on
    write. Both keep working at runtime, which is what makes them easy to miss.
