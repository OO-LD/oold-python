# Object Graph Mapping

oold-python's core feature is *IRI-transparent references*: a link field can hold either a Python object or an IRI string. The library resolves IRIs on first access via the registered backend.

## Recommended declaration

Declare a link with `Link[T]` or `LinkList[T]` as the annotation; nothing else
is needed:

```python
from typing import Optional

from oold.model import Link, LinkedBaseModel, LinkList

class Person(LinkedBaseModel):
    id: str
    name: str | None = None
    employer: Optional[Link["Organization"]] = None  # optional, like any other field
    knows: LinkList["Person"]                        # required, like a bare `id: str`
```

The annotation is the single source of truth. It names the target, so
`x-oold-range` is derived from it and written into the emitted schema - passing
`range=` would state the same thing twice and let the two disagree. It says the
field is a link, so `link=True` is redundant. And it declares requiredness and
optionality, following the pydantic convention: a bare `Link[T]` is required
and reads as `T`; `Optional[Link[T]] = None` is optional and reads as
`T | None`.

This is also the only form a type checker reads correctly in **both**
directions - the resolved object you get back, and the object, IRI or JSON
object you may assign.

Where the annotation cannot say it - a union arm such as
`str | Location | None` - mark the field with `OoldField(link=True)`.

Still supported, not recommended for new code:

| form | why not |
|---|---|
| `Optional[Bar] = Field(None, json_schema_extra={"range": "Bar.json"})` | the legacy notation, and what code generation still emits. Untyped in both directions |
| `Optional[Bar] = OoldField(range="Bar.json")` | repeats what the annotation already says |

Nothing existing needs rewriting; the recommendation applies to code you write
now. `Link[T]` / `LinkList[T]` require pydantic v2 - under `oold.model.v1` use
the `range=` form.

[Typed link declarations](#typed-link-declarations) explains the typing; the
full comparison is in
[the design doc](../design/graph-object-binding.md#which-notation-supports-what).

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
from typing import Optional

from oold.model import Link, LinkedBaseModel, LinkList

class Person(LinkedBaseModel):
    id: str
    name: str | None = None
    employer: Optional[Link["Organization"]] = None
    knows: LinkList["Person"]

# accepted: an object, an IRI, or a JSON object
alice = Person(id="ex:alice", knows=["ex:bob", {"id": "ex:carol"}])
alice.knows[0]        # a Person, not a str
```

Nothing changes at runtime - same resolution, same JSON Schema. Only what the
checker sees changes.

### What a link looks like in the emitted schema

A link serialises to an IRI, and the schema says so:

```json
"employer": {"type": "string", "x-oold-range": "https://example.org/Organization"},
"friends":  {"type": "array", "items": {"type": "string"},
             "x-oold-range": "https://example.org/Person"}
```

Not a `$ref` to the target. The `$ref` form is what code generation builds so
that the generated field is `Optional[Organization]` rather than a string;
published, it would describe a document this library never writes. A union arm
keeps its union - `str | Location | None` really does accept all three.

Give every link a `@context` term, and `"@type": "@id"` to make the value a
reference. A strictly array-typed property also needs `"@container": "@set"`,
or a single-element array compacts back to a bare value and no longer matches
the schema.

### Optionality is declared

`Link[T]` reads as `T`, so a chain needs no guard at every hop.
`Optional[Link[T]] = None` reads as `T | None`, because absence is then part of
the model:

```python
class Person(LinkedBaseModel):
    father: Link["Person"]                        # required; promises a Person
    mother: Optional[Link["Person"]] = None       # may legitimately be absent

person.father.father.father.name    # no guards
```

A link whose read type is non-optional raises when the read cannot keep the
promise - `LinkNotSet` when nothing is stored, `LinkUnresolvable` when a
reference is stored but the backend does not return the object. Both derive
from `LinkNotResolved`, so one `try/except` covers a whole walk. The message
names the failing subject, `Person(ex:p3).father ...`, because in a
self-referential chain every hop shares the class and attribute name.

Over sparse data - where a record may genuinely lack the property - the
required form would make such records unconstructible. Either declare the
`None` arm and terminate the walk on `None`, or decouple the two axes with the
escape hatch:

```python
from oold.model import LinkNotResolved

class Person(LinkedBaseModel):
    # reads as Person (chains guard-free), but the schema does not demand it
    father: Link["Person"] = OoldField(required=False)

try:
    while True:
        person = person.father
        print(person.name)
except LinkNotResolved:
    print("ancestry ends here")
```

A **transport failure is not absence** - a connection error propagates unchanged
rather than being reported as a missing link. And the single `except` covers the
walk's own links, not everything resolution does: constructing a traversed
document that is missing a *different* required link raises that class's plain
`ValueError`, which `except LinkNotResolved` does not catch. Where the walked
documents are allowed to be partial, their required links need `required=False`
too.

### `OoldField` arguments

All keyword-only, all optional:

```python
OoldField(required=None, range=None, link=None, **field_kwargs)
```

| argument | effect |
|---|---|
| `required` | **override** for what the annotation already states. Omitted, requiredness follows the annotation; `required=False` on a non-optional annotation keeps the strict read while the property stays out of the schema's `required` array |
| `range` | target schema IRI, emitted as `x-oold-range`. **Do not pass it**: omitted, it is derived from the annotation, which already names the target |
| `link` | marks the field a link where the annotation does not imply it, as in a union arm. Redundant with `Link[T]` / `LinkList[T]` |
| `required_iri` | deprecated spelling of `required`, kept because generated packages pass it |
| `**field_kwargs` | passed to `pydantic.Field` (`alias`, `description`, `default_factory`, ...). `default=None` is supplied unless you pass a `default_factory` |

Requiredness follows the annotation, exactly as for every other pydantic field:

```python
father: Link["Person"]                             # required
father: Optional[Link["Person"]] = None            # optional
father: Link["Person"] | None = None               # optional, same statement
father: Link["Person"] = OoldField(required=False) # escape hatch, see below
```

A required link raises `ValueError` at construction when it is not supplied,
and the property appears in the emitted schema's `required` array.

!!! note "`x-oold-required-iri` is internal"
    A schema states requiredness through `required` and nothing else.
    `x-oold-required-iri` is an oold-python annotation on a *field*: it carries
    the requirement across the point where code generation has to drop the
    property from `required`, so the generated field is `Optional` - a link can
    never be required at the pydantic level, because its value is routed out of
    the payload before validation. It does not appear in a published schema.

### The notation table

Every supported spelling, with what each column means: *required* is the
construction contract (`ValueError` when omitted), *read type* is what the
attribute yields, *unset read* is what reading an absent link does, and
*in `required[]`* is the emitted schema.

| spelling | required | read type | unset read | in `required[]` |
|---|---|---|---|---|
| `Link[Org]` | yes | `Org` | raises | yes |
| `Link[Org] = OoldField(...)` | yes | `Org` | raises | yes |
| `Optional[Link[Org]] = None` | no | `Org \| None` | `None` | no |
| `Link[Org] \| None = None` | no | `Org \| None` | `None` | no |
| `Optional[Link[Org]] = OoldField(...)` | no | `Org \| None` | `None` | no |
| `Link[Org] = OoldField(required=False)` | no | `Org` | raises | no |
| `Link[Org] = OoldField(default="ex:o")` | no | `Org` | never unset - the default resolves | no |
| `LinkList[Org]` | yes | `LinkResultList[Org]` | raises | yes |
| `LinkList[Org] = OoldField(required=False)` | no | `LinkResultList[Org]` | raises | no |
| `Optional[LinkList[Org]] = None` | no | `LinkResultList[Org] \| None` | `[]` | no |
| `LinkList[Org \| None] = OoldField()` | no | `LinkResultList[Org \| None]` | element is `None` | no |

A declared default makes a link not required, as it does for every pydantic
field; `required` means the *key* must be present, so an explicitly empty list
satisfies a required `LinkList` - exactly what JSON Schema `required` says
about the document `{"f": []}`.

The three optional `LinkList` forms say different things: the list itself may
be absent, an element may not resolve, every element resolves. The first two
are the same at runtime - both read `[]` when unset - and differ only
statically. Two deprecated spellings keep working: `Link[T | None]` for the
to-one case (prefer `Optional[Link[T]]`), and `list[Link[T]]` for the to-many
case (prefer `LinkList[T]`) - note the latter now derives requiredness like
`LinkList[T]` does, so a bare `list[Link[T]]` is required and needs a `None`
arm or a default to stay optional. One deliberate deviation from plain
pydantic: a bare `Optional[Link[T]]` *without* `= None` is treated as optional,
because a link's value never reaches pydantic's own required check - write the
`= None`.

`OoldField(required=False)` is the one escape that decouples the two axes: the
read still promises an `Org` - a chain needs no guard, an unset read raises
`LinkNotSet` - while the schema does not demand the property. It is **not
expressible in JSON Schema**, so it never round-trips through a schema and the
generator never emits it. Prefer `Optional[Link[T]] = None` unless the
guard-free chain is the point.

### List access and filters

Element access and the query DSL act on `LinkResultList[T]` and preserve `T`,
so the declaration decides what a filtered result holds:

| declaration | `links[0]` | `links[0:2]` | `links[Person.name == "x"]` | `links["@name=='x'"]` |
|---|---|---|---|---|
| `LinkList[Org]` | `Org` | `LinkResultList[Org]` | `LinkResultList[Org]` | `Any` |
| `LinkList[Org \| None]` | `Org \| None` | `LinkResultList[Org \| None]` | `LinkResultList[Org \| None]` | `Any` |
| `Optional[LinkList[Org]] = None` | gate with `is not None` first: the attribute reads `LinkResultList[Org] \| None` | same | same | same |

Two static imprecisions, stated rather than fixed: a condition filter over
`LinkList[Org | None]` keeps the `None` arm although a `None` element can never
match a condition, and the inline string form returns `Any`, which ends type
checking downstream - prefer the `Person.name == "x"` form.

!!! note "Write `LinkList[T]`, not `list[Link[T]]`"
    The to-many form is its own type. `list[Link[T]]` keeps working at runtime
    but a checker reads it as a list of descriptors. For the to-one optional
    form, `Optional[Link[T]]` is the recommended spelling; note that its
    *write* side is checker-dependent - pyright applies the descriptor's
    assignment type through the union, ty does not, so an attribute write
    through the wrapper types only under pyright; pass the reference at
    construction instead (read narrowing is correct everywhere).
