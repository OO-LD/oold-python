# Graph-object binding and code generation: a design reflection

Status: draft for discussion, tracked in [oold-python#107].

Companion prototypes, all runnable and under `src/oold/experimental/`:

| module | what it explores |
|---|---|
| `auto_descriptor_binding.py` | **recommended.** Descriptors installed automatically from annotations; unchanged declaration syntax |
| `notation.py` | the reviewed notations: `OoldField()` / `link=True`, `Link[T]` inside annotations, union arms |
| `descriptor_binding.py` | the same binding declared explicitly as unannotated descriptors |
| `ref_binding.py` | explicit `Ref[T]` handle for visible / async resolution |
| `codegen_spike.py` | IR-based code generation without text post-processing |

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

Confirmed on **pyright and mypy**. Annotated declarations type natively; the
unannotated descriptor form types through overloaded `__get__` (the
SQLAlchemy-relationship pattern):

```
p.knows          -> List[Person]        (LinkList["Person"]() - subscript only)
p.knows[0].name  -> str
p.employer       -> Organization | None (Link(Organization))
p.knows[0].nope  -> error: Cannot access attribute "nope" for class "Person"
```

`LinkList["Person"]()` needs no second argument: the subscript carries the
static type, `__orig_class__` the runtime target.

### 3.3 Declaration notations

Four notations are supported; all share one descriptor implementation, and they
can be mixed in a single class.

```python
class Person(OoldModel):
    id: str
    name: Optional[str] = None

    # 1. implicit, zero-config - target inferred from the annotation
    knows: Optional[List["Person"]] = OoldField()

    # 2. explicit link marker inside the annotation
    employer: Optional[Link[Organization]] = Field(default=None)
    friends: Optional[List[Link["Person"]]] = OoldField()

    # 3. union arms: literal text | inline object | reference
    location: Union[str, Location, None] = OoldField(link=True)

    # 4. unannotated descriptor (descriptor_binding.py variant)
    #    addresses = LinkList(Address)
```

`Link[T]` is `Annotated[T, LinkMarker()]`, so a checker reads it as `T` - and
unlike the rejected form in 3(c) the runtime value really *is* a `T`, because
the descriptor returns the resolved object. The union arms discriminate at
construction: a bare string stays a literal when a `str` arm is declared, a
`{"@id": ...}` object is a reference, and any other object is inline. An inline
object with no `@id` cannot be emitted as a reference, so it serialises nested -
a blank node.

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
- **Code generation:** move off text post-processing toward an IR-based
  generator, staging through a hybrid that first deletes the regex. Fold
  `osw-python`'s `fetch_schema` orchestration and the package-generator passes
  into it.
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
