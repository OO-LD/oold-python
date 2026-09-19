# Graph-object binding and code generation: a design reflection

Status: draft for discussion, tracked in [oold-python#107].

The recommended binding has been promoted out of the prototypes and now lives in
the package proper:

| module | what it is |
|---|---|
| `src/oold/model/_descriptor.py` | **the binding.** Descriptors installed from annotations, the `Link[T]` / `LinkList[T]` notation, the query DSL |
| `src/oold/model/v1/_descriptor.py` | the same for pydantic v1 |
| `src/oold/model/_compat.py` | the downstream API surface (`__iris__`, `get_iri_ref`, `to_json` ...) |
| `src/oold/model/_notation.py` | the reviewed notations on top of it: `OoldField()`, union arms |
| `src/oold/experimental/codegen_spike.py` | IR-based code generation without text post-processing (still a spike) |

It **is** `oold.model.LinkedBaseModel`; the legacy per-attribute-interception
binding is reachable with `OOLD_DESCRIPTOR_BINDING=0`, and
`oold.model.LINK_NOTATIONS_ACTIVE` reports which is in force.

It took two attempts. The first flip rested on three downstream suites passing,
which was necessary and not sufficient: a review then found seven behaviours the
binding did not reproduce - `BaseController.to_json()` stripping every data
field, `FieldProxy` losing truthiness and default forwarding,
`x-oold-required-iri` enforced nowhere, `__iris__` assignment merging instead of
replacing, `get_raw` answering `[None]`, an inline linked object without an IRI
being dropped, and unset links vanishing from `model_dump()`. None of those
paths were reached by any suite. The default was withdrawn, each was fixed with
a test in `tests/test_compat_parity.py` that fails without its fix, and the
binding was made the default again on that basis rather than on suite results
alone.

Verification scripts under `examples/`: `check_binding_features.py` (requirement
matrix), `bench_binding_variants.py` (per-operation benchmarks),
`bench_attribute_access.py` (where the interception cost comes from).

This document asks the questions the OO-LD v0.8 migration hinges on:

1. Is the current object-graph binding the best approach we can build in Python?
2. Would the problem be easier in another language, and what does that tell us?
3. What would a linked-data-native language look like?
4. Given how much of the toolchain is patch code around
   `datamodel-code-generator`, should we write our own generator?

## 1. What the binding must do

A property whose value is another entity can be written two ways in the same
field: inline as a nested object, or by reference as an IRI string (annotated
`x-oold-range`, legacy `range`). The binding layer has to **construct** from
either form, **resolve** an IRI lazily through a pluggable backend,
**serialise** references back to IRIs in JSON and JSON-LD, and keep **static
typing** so the declared type is the target model.

Beyond that minimum, the shipped library also provides polymorphic resolution
(dispatch on the instance type IRI), batched list resolution, rich list
operations, and a class-level query DSL. All of these are requirements, not
extras: they are verified per variant in `check_binding_features.py`.

## 2. Critique of the current approach

`src/oold/model/__init__.py` intercepts attribute access unconditionally:

- **Global monkeypatch.** `pydantic.fields.FieldInfo` is replaced process-wide
  at import (`model/__init__.py:57`). Any code importing `oold.model` inherits a
  patched pydantic.
- **Metaclass attribute interception.** `LinkedBaseModelMetaClass` overrides
  `__getattribute__` (`:157`) for the class-level query DSL, needing a
  `_constructing` guard (`:119-132`) to avoid corrupting pydantic's own
  metaclass bookkeeping.
- **Instance interception plus a parallel state dict.** Each instance overrides
  `__getattribute__` / `__setattr__` (`:625-673`); every read consults the
  `__iris__` side-dict (`:399`) and may perform synchronous backend I/O inside
  the getter. `__iris__` duplicates field state, forcing heavy `__init__`
  special-casing (`:474-582`) and a bespoke list type (`:223`).
- **Import-order-dependent registries** `_types` / `_controller_types` (`:109`).

### Cost, measured

`examples/bench_binding_variants.py`, 100k iterations per operation, best of 5,
each variant in its own process. `(x)` is relative to plain pydantic v2 reads.

| variant | plain read | plain write | link read | link write | query build |
|---|---:|---:|---:|---:|---:|
| plain pydantic v1 | 3.5 (0.7x) | 47.9 (9.8x) | na | na | na |
| plain pydantic v2 | 4.9 (1.0x) | 23.9 (4.9x) | na | na | na |
| gated `__getattribute__` | 19.8 (4.0x) | 69.0 (14.1x) | na | na | na |
| shipped v1 | 58.1 (11.9x) | 959.9 (195.8x) | 426.2 (86.9x) | 1590.4 (324.4x) | 286.9 (58.5x) |
| shipped v2 | 93.3 (19.0x) | 572.5 (116.8x) | 838.1 (171.0x) | 1140.8 (232.7x) | 490.1 (100.0x) |
| **auto-descriptor** | **5.1 (1.0x)** | **50.1 (10.2x)** | **6.3 (1.3x)** | **270.8 (55.2x)** | **194.6 (39.7x)** |
| explicit `Ref[T]` | 4.9 (1.0x) | 24.4 (5.0x) | 5.8 (1.2x) | 27.6 (5.6x) | na |

Every attribute of every `LinkedBaseModel` - including fields that are not
references - pays roughly 12x (v1) to 19x (v2).

### Could the interception just be gated on range annotations?

Partly. Early-exiting for non-link fields removes most of the *work* (19x down
to ~3.1x for an idealised closure-frozenset gate, ~4.5x for a realistic
per-class one), but not the *call*: defining `__getattribute__` at all forces a
Python-level function call on every access instead of the C-level slot. The gate
shrinks the body, not the call. A descriptor is that same gate implemented in C.

## 3. Python alternatives

**(a) Per-field descriptors (recommended).** Only `x-oold-range` fields become
descriptors, so plain fields keep native access. Plain attribute access returns
the **real** resolved object, so `isinstance` holds and the value passes
anywhere the target type is expected.

**(b) Explicit `Ref[T]` (opt-in).** A reference is a first-class value with
`resolve()` / `await aresolve()`. Resolution becomes visible, batchable and
awaitable - none of which the shipped design can express. Cost: `p.knows[0]` is
a `Ref`, not a `Person`, so `isinstance` fails.

**(c) The trap: do not dress (b) up as (a).** Declaring a `Ref` field as
`Annotated[Person, ...]` makes a checker read it as `Person` while the runtime
value is a `Ref`. `isinstance` is `False`; the static type is not backed by the
runtime value. Rejected.

### 3.1 The key optimisation: non-data descriptor plus instance-dict cache

The descriptor is deliberately **non-data** (it defines `__get__` but not
`__set__`) and stores the resolved value in the instance `__dict__`. Because an
instance dict entry shadows a non-data descriptor, every subsequent read is a
plain C-level dict lookup that never re-enters Python - the
`functools.cached_property` pattern. Writes remain intercepted by a targeted
`__setattr__`, which pops the entry to invalidate it.

Caching in a pydantic `PrivateAttr` instead costs a Python-level `__getattr__`
per read, which is what made link reads slow:

| link read (warm) | time | vs plain field |
|---|---:|---:|
| data descriptor + `PrivateAttr` cache | 336.0ms | 31.8x |
| **non-data descriptor + `__dict__` cache** | **10.5ms** | **1.00x** |
| plain pydantic field (baseline) | 10.6ms | 1.00x |

A **32x** improvement on the hot path; link reads drop from 33.6x to 1.3x in the
full matrix. Both descriptor prototypes use it.

### 3.2 Static typing

A link has **two** types and one annotation can only state one of them. What you
read is a resolved object; what you may write is that object *or* a reference to
it - an IRI string, or a JSON object still to be constructed. Since pydantic's
`dataclass_transform` takes the annotation as the `__init__` parameter type,
`knows: list[Person]` necessarily rejects `knows=["ex:bob"]`.

The only mechanism in the typing spec that carries both is the **descriptor
protocol** (PEP 681): when the annotation *is* a descriptor type, a checker takes
the `__init__` parameter and the assignment type from `__set__` and the attribute
type from `__get__`. `Link[T]` and `LinkList[T]` are therefore usable as the
whole annotation:

```python
class Person(LinkedBaseModel):
    knows: LinkList["Person | None"] = OoldField()
    employer: Link[Organization] = OoldField()
```

`__set__` is declared under `TYPE_CHECKING` only, so at runtime the descriptor
stays **non-data** and the instance-`__dict__` cache from 3.1 is untouched.
`__get_pydantic_core_schema__` builds the schema of the *target*, so what
pydantic sees is identical to the plain annotation - arrays, unions and forward
references included, and both spellings therefore emit the same document.

What that document says about a link is a separate question. A link serialises
to an IRI, so the published property is `{"type": "string", "x-oold-range": …}`,
or an array of strings for a to-many link - which is what a real OSW schema
carries. The `$ref` / `allOf` form is what `generator.preprocess` builds so that
`datamodel-code-generator` emits `Optional[Bar]` instead of a string field; it
is a code generation shape, and publishing it described a document the library
never writes. A union arm keeps its union: `str | Location | None` genuinely
accepts a literal, a reference or an inline object.

#### Optionality is declared, not assumed

`Link[T]` reads as `T`, not `T | None`. The declaration is a promise the binding
keeps, so a chain of mandatory links needs no guard per hop:

```python
class Person(LinkedBaseModel):
    father: Link["Person"] = OoldField()          # mandatory
    mother: Link["Person | None"] = OoldField()   # optional

person.father.father.father.name    # no guards - the type says it resolves
mother = person.mother              # guard required, and warranted
```

Without this, every hop needs an `is not None` check and chaining collapses -
the type would be truthful and useless at once. Handing back a `None` the
declaration denies is the alternative, and that is the same polite fiction the
`Annotated`-over-`Ref` form was rejected for in 3(c).

What the promise costs, by case:

| | `Link[T]` | `Link[T \| None]` |
| --- | --- | --- |
| not set, no IRI | **raises `LinkNotResolved`** | `None` |
| backend error | propagates | propagates |
| answered, no such entity | **raises `LinkNotResolved`** | `None` |

All three fire on *access*, not at construction. An earlier version rejected an
absent mandatory link when the object was built - knowable without resolving
anything, and tempting for that reason - but it over-enforces: the annotation
says what *reading* the link yields, not that every instance carries one. Graph
data is routinely partial (most Wikidata people have no recorded father), and
rejecting those objects makes them unloadable. Declaring a link mandatory states
an intent to **traverse** it, so one `try/except` around a whole walk replaces a
guard at every hop.

The middle row is unchanged and matters: a transport failure is not "has no
father", and conflating the two would be the real bug.

#### Coverage

| spelling | read | write by IRI | runtime |
| --- | --- | --- | --- |
| `Link[Organization]` | `Organization` | typed | mandatory |
| `Link[Organization \| None]` | `Organization \| None` | typed | optional |
| `LinkList["Person"]` | `LinkResultList[Person]` | typed | mandatory elements |
| `LinkList["Person \| None"]` | `LinkResultList[Person \| None]` | typed | optional elements |
| `list["Person"]` | `list[Person]` | not typed | optional |
| `Optional[Organization]` | `Organization \| None` | not typed | optional |
| `knows = LinkList("Person")` | `LinkResultList[Person]` | n/a - no field | optional |

Every spelling except the two `Link[...]` forms stays optional, so existing
declarations - including everything the generator emits - behave exactly as
before. Consumers that want reference assignment enforced on generated models can
scope the rule per file rather than repo-wide: ty supports
`[[tool.ty.overrides]]` with an `include` glob.

A to-many link keeps the slot of an unresolvable reference, so the list stays
aligned with the stored references - as `None` when the element type admits it,
otherwise as a raise. A query result is different: it answers with what it found,
so an IRI it could not place is dropped rather than kept.

Both **pyright and ty** resolve all of it, including `Model[...]` through the
metaclass `__getitem__` overloads. `tests/typing/links.py` and
`tests/typing/query_dsl.py` are checked by both.

One environment trap is worth knowing, because it fails silently rather than
loudly: if the configured environment cannot resolve pydantic, ty reports a
spurious `conflicting-metaclass` on every model and then infers `Unknown` for
class subscription - so every `assert_type` passes vacuously. `tests/test_typing.py`
therefore points ty at the interpreter running the tests, not at `./.venv`.

### 3.3 Declaration notations

**Recommended: `Link[T]` / `LinkList[T]` as the whole annotation, with a bare
`OoldField()`.**

```python
class Person(LinkedBaseModel):
    id: str
    employer: Link["Organization | None"] = OoldField()
    knows: LinkList["Person"] = OoldField()
```

The annotation is the single source of truth: it names the target, says the
field is a link, and declares optionality. So `range=` is not passed - it would
state the target twice and let the two disagree - and `link=True` is redundant.
`x-oold-range` is derived from the annotation when the schema is generated,
which is what keeps the emitted schema a link schema.

Deriving rather than repeating had to wait for the right moment to do it. A
forward reference is not resolvable when the descriptor is installed, and a
`Field()` object is shared between models, so its `json_schema_extra` must not
be mutated in place. `__get_pydantic_json_schema__` has neither problem.

Every other notation is supported and keeps working - including the legacy
`Field(None, json_schema_extra={"range": ...})` that code generation still
emits - but each gives something up, and the table after the example says what.
`Link[T]` / `LinkList[T]` are pydantic v2 only; `oold.model.v1` keeps the
`range=` form.

Four notations are supported; all share one descriptor implementation, and they
can be mixed in a single class.

```python
class Person(OoldModel):
    id: str
    name: Optional[str] = None

    # 1. Link[T] / LinkList[T] as the whole annotation - typed both ways (3.2)
    knows: LinkList["Person"] = OoldField()
    employer: Link[Organization] = OoldField()

    # 2. implicit, zero-config - target inferred from the annotation
    friends: Optional[List["Person"]] = OoldField()

    # 3. union arms: literal text | inline object | reference
    location: Union[str, Location, None] = OoldField(link=True)

    # 4. unannotated descriptor - no annotation, so no static type at all
    #    addresses = LinkList(Address)
```

All four are the same field at runtime and produce the same JSON Schema; they
differ only in what a type checker can see, per the coverage table in 3.2. The
union arms discriminate at
construction: a bare string stays a literal when a `str` arm is declared, a
`{"@id": ...}` object is a reference, and any other object is inline. An inline
object with no `@id` cannot be emitted as a reference, so it serialises nested -
a blank node.

#### Which notation supports what

Every row is the same field at runtime - they resolve, batch, serialise and
query identically. They differ in what a type checker sees and what reaches the
JSON Schema. Measured, not asserted: read types from `ty`, schema keys from
`model_json_schema()`.

| notation | codegen emits it | target inferred | range keyword in schema | read type | IRI write typed | optionality declarable |
|---|---|---|---|---|---|---|
| `Optional[List[T]] = Field(None, json_schema_extra={"range": ...})` | yes | no | `range` (legacy) | `list[T] \| None` | no | no |
| `= OoldField(range="...")` | no | no | `x-oold-range` as given | as annotated | no | no |
| `= OoldField()` | no | **yes** | **`x-oold-range`, derived** | as annotated | no | no |
| `Link[T]` / `LinkList[T]` with `OoldField()` | not yet | **yes** | **`x-oold-range`, derived** | **exact** (`T`, `LinkResultList[T]`) | **yes** | **yes** |
| `= Link(T)` / `= LinkList(T)` | no | yes (from the argument) | **field absent from schema** | exact | n/a - not a field | no |
| `str \| Location \| None = OoldField(link=True)` | no | yes | **derived** | union as declared | no | via the `None` arm |

The derived range is the target's `get_cls_iri()`, taken at schema-generation
time; an explicit `range=` is never overwritten, and a target that cannot name
itself contributes nothing, leaving the `x-oold-link` marker in place. The
unannotated descriptor form is not a pydantic field at all, so it neither
appears in the schema nor gets an `__init__` parameter, though its read type is
exact.

#### Requiredness is a field argument, not the annotation

Two different questions - "must the caller supply it?" and "what do I get when I
read it?" - so two carriers:

| declaration | stored as | enforced | on violation |
|---|---|---|---|
| `Link[T]` - no `None` arm | `_AutoLink.optional = False` | on read | `LinkNotResolved` |
| `OoldField(required=True)` | `_AutoLink.required_iri`, precomputed into `cls.__required_links__`; reaches the schema as the standard `required` array | in `__init__` | `ValueError: ... is required but not set` |

A link is never required at the *pydantic* level, because its value is routed
out of the payload before validation - which is why the legacy binding declared
every generated link field `Optional[...]` and carried requiredness in the
keyword. `x-oold-required-iri` is that keyword, and it stays internal: a schema
states requiredness through `required` alone, and the annotation exists only to
carry the requirement across the point where code generation drops the property
from `required` so the emitted field is `Optional`.

A bare `Link[T]` annotation with no default is **optional**. "No default means
required" reads well in plain Python, but requiredness propagates into
resolution - the failure mode described next - and links are declared far more
often than they are required, so the terse form is the common case.

**Why not put requiredness in the annotation.** `required` -> `Link[T]`,
absence -> `Link[T | None]` reads well and was the first proposal. It fails on a
self-referential link. `father: Link["Person"]` required means every person in
the dataset carries a father IRI, which is only true of a graph with no root -
and resolution constructs target objects, so the failure surfaces one hop from
its cause: reading `alice.father` raises `ValueError: father is required but not
set` about *Bob's* document, which you never asked for. So `father` would have
to be `Link["Person | None"]`, which needs a guard per hop - the thing the
annotation exists to avoid.

The alternative was to strip the `| None` under `TYPE_CHECKING`, which both
pyright and ty do resolve (a self-type overload on `Link[X | None]` yields `X`).
It was rejected because the runtime would then have to raise instead of
returning `None`, which silently breaks `entity.link is None`, `if entity.link:`
and `getattr(entity, f, None)` - and the last does *not* save the caller, since
`LinkNotResolved` is a `LookupError`, not an `AttributeError`. Pattern A in
`downstream-migration.md` is exactly that shape.

Suppressing the diagnostic instead is only half-available: pyright separates
`reportOptionalMemberAccess` from `reportAttributeAccessIssue`, so it can be
turned off without losing typo detection, but ty reports both under
`unresolved-attribute` (checked on 0.0.49 and 0.0.80). Either way it is a
setting every downstream consumer would have to make.

**Open:** nothing emits the read-side promise, so a model -> schema -> model
round trip loses the distinction between `Link[T]` and `Link[T | None]`. Code
generation can default to `Link[T]` for required properties and
`Link[T | None]` otherwise; expressing it exactly needs a keyword of its own.

#### Notations considered and dropped

| notation | why it is not used |
|---|---|
| `list[Link[T]]` - `Link` nested inside a container | Silently degrades. A descriptor nested in a `list` is not treated as one, so the read type comes back as `list[Link[T]]` - not merely untyped but **wrong**. Superseded by `LinkList[T]`, which carries the to-many-ness itself. Still works at runtime, which is what makes it dangerous. |
| `Optional[Link[T]]` - `Link` nested inside a union | Half-degrades: the read type narrows to `T \| None` correctly, but the descriptor's `__set__` is not seen through the wrapper, so assigning an IRI is rejected (`Expected Link[T] \| None`). `Link[T \| None]` states the same thing and types both directions. |
| `Annotated[Person, OoldRange(...)]` wrapping a `Ref` value | The static type is not backed by the runtime value: a checker reads `Person`, `isinstance` says `Ref`. Rejected in 3(c). |
| `Ref[T]` as the field type | Honest, but `p.knows[0]` is a `Ref`, not a `Person` - `isinstance` fails and the list operations, polymorphic dispatch and query DSL go with it (3.6). Kept only as an opt-in handle for visible or async resolution. |
| `~Person.name == "x"` for match filters | `~` binds tighter than `==`, so this parses and would work - but pandas established `~` as NOT, and colliding with that is worse than a method. |

Two **semantics** were dropped along the way, for the record: elements of a
to-many link were briefly `T | None` unconditionally (replaced by declaring it),
and a mandatory link was briefly rejected at construction rather than on access
(see the table above).

### 3.4 Typed `json_schema_extra`

The raw dict can be replaced by a validated class, but it **must subclass
`dict`**: pydantic merges extras via `isinstance(json_schema_extra, dict)`, so a
plain `BaseModel` is accepted at declaration and then silently dropped from the
schema. `OoldExtra` delegates validation to a pydantic model and exposes typed
properties, so runtime code stops doing `extra["x-oold-range"]`.

```python
OoldExtra(range="")   # ValidationError: String should have at least 1 character
extra.range           # typed read (str)
```

Pass the payload to `model_validate` as a dict rather than as aliased kwargs,
otherwise type checkers reject `range=` as "No parameter named".

### 3.5 Query DSL

Preserved, and cheaper. It moves from `__getattribute__` (every access) to
`__getattr__` (a fallback, only when lookup *fails*). Pydantic v2 removes field
names from the class namespace, so `Person.name` fails naturally and lands
there at no cost to anything else. For link fields no metaclass is involved at
all: the descriptor's `__get__(None, owner)` returns the descriptor on class
access, so comparison operators live directly on it.

`__getattr__` on the metaclass must never call `getattr(cls, ...)`:
`cls.model_fields` is a property that itself calls `getattr`, which recurses
until the stack overflows. Read `klass.__dict__["__pydantic_fields__"]` along
the MRO and reject `_`-prefixed names.

**Static types.** The condition expression itself cannot be typed: `Entity.name`
is a declared field, so pydantic's `dataclass_transform` makes the annotation
authoritative for class-level access too and the `FieldProxy` really returned is
invisible, leaving `Entity.name == "x"` as `bool`. The shipped binding handles
this by accepting `bool` in the `__getitem__` overloads, and the descriptor
binding does the same: the argument type stays wrong, the result type comes out
right. What the subscript yields is fully typed:

| expression | static type |
| --- | --- |
| `Entity["ex:e1"]` | `Entity \| None` |
| `Entity[Entity.name == "x"]` | `LinkResultList[Entity] \| None` |
| `...[0]` | `Entity` |
| `...[cond]` | `LinkResultList[Entity]` |

`LinkResultList` is generic in the item type, which is what keeps the item type
through indexing and filtering. Accepting `bool` there widens
`list.__getitem__`, which answers `T` for a `bool` index - a deliberate
divergence, since indexing a list by `True` is not something anyone writes.
`tests/typing/query_dsl.py` pins these with `assert_type`;
`tests/test_typing.py` runs pyright over it.

The `| None` is the one difference from the shipped overloads, which promise a
bare `M`: the query really does return `None` when nothing matches, so the
stricter type is the truthful one.

Instance-level filtering (`entity.links[cond]`) is typed only when the field is
annotated `LinkResultList[T]`. The `list[T] | None` form the current codegen
emits stays unfiltered at the type level, so the generator should emit
`LinkResultList[T]` for to-many links.

#### The DSL against a real query language

A `Condition` is consumed by two things, and the check that matters is that they
agree: `apply_operator`, which filters objects already in memory, and the SPARQL
resolvers, which have to ask a triple store the same question. `query()` on
`SparqlResolver`, `LocalSparqlResolver` and `WikiDataSparqlResolver` translates
`eq, ne, lt, le, gt, ge` and `&`; anything else raises rather than quietly
returning the wrong rows.

Two things fell out of doing it, which is why it was worth doing before adding
more operators:

- **The predicate and the literal both come from the model's own context.** A
  probe document is expanded through it, so a term scoped `@language: en` yields
  `"x"@en` and one with an `@type` yields `"x"^^<xsd:integer>`. Deriving either
  by hand would be a second, divergent reading of the same context.
- **A match needs a type constraint.** `rdfs:label "Tim Berners-Lee"@en` also
  matches a book edition, and resolving that fails on an unknown type IRI. The
  Wikidata resolver constrains on P31 - the predicate it already rewrites into
  `@type` on the way in.

`tests/test_sparql_query.py` asserts the SPARQL answer against `apply_operator`
over the same data rather than against hand-written expectations, so it tests
the agreement rather than one implementation twice. It runs offline against an
rdflib graph.

Still missing, and visible from here: there is no `|` (the model defines
`__and__` but not `__or__`), no `~`, and link descriptors carry only `==` / `!=`,
not the ordering operators.

### 3.6 Requirement matrix

From `examples/check_binding_features.py`, which exercises each requirement
rather than asserting it.

| requirement | shipped v1 | shipped v2 | auto (implicit) | auto (explicit) | `Ref[T]` |
|---|---|---|---|---|---|
| syntax_unchanged | ok | ok | ok | FAIL | FAIL |
| build_by_iri / build_by_object | ok | ok | ok | ok | ok |
| lazy | ok | ok | ok | ok | ok |
| real_object (`isinstance`) | ok | ok | ok | ok | FAIL |
| polymorphic | ok | ok | ok | ok | FAIL |
| batched | ok | ok | ok | ok | FAIL |
| cached | ok | ok | ok | ok | ok |
| mutation | ok | ok | ok | ok | FAIL |
| link_validated | ok | ok | ok | ok | ok |
| list_lookup / list_filter | ok | ok | ok | ok | FAIL |
| list_projection | FAIL | FAIL | **ok** | ok | FAIL |
| serialize_iri | ok | ok | ok | ok | ok |
| query_dsl | ok | ok | ok | ok | FAIL |
| typed_extras | FAIL | FAIL | **ok** | ok | FAIL |
| no_monkeypatch | FAIL | FAIL | **ok** | ok | ok |

The descriptor binding is a **strict superset** of the shipped one. Note the
shipped implementation *does* batch list resolution - an earlier claim to the
contrary was wrong.

On validation: the parent's *field* validation is bypassed (the descriptor
shadows the field), but the linked object is still validated **at construction
of the linked class**, which is where its constraints live.

## 4. Would another language do better?

The shipped design makes *every* attribute transparently resolve. Python has no
cheap whole-object proxy, so that choice forces `__getattribute__` plus a
metaclass. Per-field descriptors avoid it entirely.

- **JavaScript / TypeScript.** `Proxy` is a language primitive, so transparent
  lazy references are idiomatic and cheap (LDO, rdf-ts).
- **Rust / TreeLDR.** Compiles a linked-data schema to typed Rust plus a JSON-LD
  context; references are an id newtype (`IdRef<T>`) and resolution is explicit
  I/O - essentially the `Ref[T]` design enforced by the type system.
- **Java / twa, TheWorldAvatar OGM.** Annotation-driven mapping resolving
  through a session object; explicit, not getter-side-effect.
- **Clojure / Datomic.** No object graph at all: entity-attribute-value tuples,
  a reference is an entity id, and resolution is an explicit `pull` with a
  declared shape.

Every ecosystem that handles this well makes resolution **explicit** or has a
**language-level proxy**. Python has neither at whole-object level, but the
descriptor protocol is exactly the per-field equivalent, and `Ref[T]` covers the
explicit camp. Supporting both matches the two durable designs rather than
picking one.

## 5. What would a linked-data-native language look like?

- **IRIs and language-tagged strings as primitive types**, not `str`.
- **Identity and type first-class on every value**; open-world structural typing
  aligned to SHACL shapes rather than closed classes.
- **Lexical namespaces / contexts**, so `name` resolving to `schema:name` is a
  compile-time fact.
- **References transparent, resolution an effect.** Reading a linked value is
  ordinary syntax, but resolution is tracked by an effect / capability (like
  `async`) served by a pluggable resolver: transparency without hidden, untyped
  I/O.
- **Graph literals and query comprehensions** as language constructs.
- **Built-in JSON-LD / RDF serialisation**, because the object model *is* the
  RDF model.

Prior art: N3, Shen, LinkML, TreeLDR, RDF-star, Datomic/Datalog, GraphQL-LD.

The recommended binding already approximates the ideal: reads look ordinary and
return real objects, while `.refs()` / `aresolve()` expose resolution as an
explicit, batchable, awaitable effect. What Python cannot have - IRIs as
primitives, structural open-world typing - is exactly what argues for keeping
the source of truth in the schema and generating the binding from it.

## 6. Own generator vs datamodel-code-generator

Code generation currently fights the tool from both ends: `src/oold/generator.py`
monkeypatches the parser and regex-fixes its output; `src/oold/utils/codegen.py`
subclasses it to inject `@context` and repair `allOf`; and the external
`osw-python-package-generator` post-processes the generated *text* with roughly
1100 lines of regex (`_fix_missing_allof_bases`,
`replace_duplicated_classes_with_imports`, UUID/OSW-ID dedup,
`replace_unit_enums`).

Those structural problems - multiple `allOf` inheritance, class identity by
`x-oold-uuid`, cross-package imports, typed `x-oold-range` references - are
graph facts the tool does not model, so they are fought after the fact on
strings.

Options: (1) keep and patch, (2) hybrid - keep the tool for plain JSON Schema
fragments but operate on its *model objects* instead of text, (3) own IR-based
generator.

`codegen_spike.py` implements a minimal option 3 and shows the three
regex-fought problems fall out for free from an IR: `allOf` becomes real
multiple inheritance, two schemas sharing `x-oold-uuid` collapse to one class,
and `x-oold-range` becomes a typed reference field - with no post-processing.

**Recommendation: option 3, staged through option 2.** The real cost is
re-implementing the JSON Schema breadth the tool gives for free (unions, enums,
constraints, formats, naming). Mitigations: stage through the hybrid; gate the
switch on a golden-file diff of a regenerated real package; keep the IR
language-agnostic so it can later emit TypeScript or Rust.

## 7. CPython and Rust optimisation potential

Applied: the non-data descriptor plus instance-dict cache (section 3.1), a 32x
win that puts warm link reads at native speed.

Remaining CPython headroom:

- **Query construction, ~6.6x available.** `Condition` is a pydantic
  `BaseModel`, so every `Cls.field == value` pays full validation: 200.1ms vs
  30.4ms for a `__slots__` class over 200k iterations. It touches the public
  `oold.backend.interface` API, so it is a deliberate change.
- **Link writes (55.2x)**, dominated by `Ref` construction and private-attr
  access on the write path.
- **Plain writes (10.2x vs 4.9x)**, entirely the extra `__setattr__` frame;
  classes with no link fields need no override at all.

Rust: after the fix above the binding hot path is a C-level dict lookup and
pydantic's validation core is already Rust, so there is little left to win
there. The real opportunities are elsewhere: **`pyld` is pure Python and
dominates RDF export** (`to_jsonld()` 120.7 us/op vs `to_json()` 19.7 us/op, a
6x gap, essentially all context expansion), and `rdflib` is likewise pure Python
where `pyoxigraph` (Rust) is an alternative for graph storage and SPARQL.
Priority: the JSON-LD/RDF layer, not the object binding.

## 8. Recommendations and impact on the migration

- **Binding:** adopt the per-field descriptor design, declared by annotation
  (unchanged syntax, so generated packages are untouched), with the explicit
  descriptor and `Link[T]` notations available and `Ref[T]` as an opt-in handle
  for visible or async resolution. Avoid the `Annotated`-over-`Ref` form.
- **Query DSL:** carried over whole, including the typed subscription overloads
  (3.5). The `_constructing` guard the metaclass carries is not a cost of the
  DSL - the descriptor needs it independently, since a descriptor is an ordinary
  class attribute that pydantic's base-attribute probe trips over without
  `__getattr__` ever being consulted.
- **Code generation:** move off text post-processing toward an IR-based
  generator, staging through a hybrid that first deletes the regex. Fold
  `osw-python`'s `fetch_schema` orchestration and the package-generator passes
  into it. Emit `LinkResultList[T]` for to-many links so instance-level
  filtering type-checks.
- **Sequencing into v0.8:** the keyword migration should read `x-oold-range` /
  `x-oold-iri` / `x-oold-uuid` (dual-read with legacy) through the same IR and
  binding, so the generator, the runtime binding and the RDF layer share one
  keyword-normalisation path rather than three.

### Open items

- **pydantic v1**: the prototypes are v2-only
  (`__pydantic_init_subclass__`, core schemas); `model/v1/__init__.py` is a full
  parallel implementation and the package generator emits both.
- **Public-API equivalence** with the shipped `LinkedBaseModel` (`to_json`,
  `to_jsonld`, `from_json`, `from_jsonld`, `cast`, controllers, `Model["iri"]`)
  must be demonstrated before adoption so `osw-python` is unaffected.
- **The class registry is still a process-wide global** keyed by type IRI, so
  two classes claiming the same IRI shadow each other and resolution depends on
  import order. The prototype reproduces the very flaw criticised in section 2;
  it surfaced as a cross-module test collision and is currently worked around by
  using distinct IRIs per test module. A scoped registry (per root model or per
  explicit registry object, with the global as a default) is needed before
  adoption.

[oold-python#107]: https://github.com/OO-LD/oold-python/issues/107
