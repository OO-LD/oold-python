# Downstream API surface and which patterns become obsolete

Companion to [graph-object-binding.md](graph-object-binding.md), tracked in
[oold-python#107].

Downstream inherits its API from `oold.model.LinkedBaseModel` through
`opensemantic.OswBaseModel`:

```
opensemantic.OswBaseModel  ->  oold.model.LinkedBaseModel  ->  pydantic.BaseModel
opensemantic.v1.OswBaseModel -> oold.model.v1.LinkedBaseModel -> pydantic.v1.BaseModel
```

`to_json`, `to_jsonld`, `from_json` and `from_jsonld` are **inherited from
`LinkedBaseModel`**, not defined by `OswBaseModel`, so replacing the binding
changes them for every consumer.

## Measured usage

Scanned: the generated `opensemantic.*-python` packages plus several
applications built on them (vendored `.venv`, `.tox` and `site-packages` copies
excluded). Application code is referred to generically below; the counts are
what matters for the compatibility decision.

| member | sites | verdict |
|---|---:|---|
| `json_schema_extra` | 2499 | v2 declaration, already supported unchanged |
| `OswBaseModel` | 246 | subclass of `LinkedBaseModel` |
| `range=` | 187 | **v1 declaration style** (extras land in `field_info.extra`) |
| `get_cls_iri` | 42 | unchanged |
| `get_iri_ref` | 24 | **keep** (see pattern E) |
| `LinkedBaseModel` | 16 | direct base-class references |
| `__iris__` | 15 | **keep, read and write** (pattern C) |
| `from pydantic import` / `.v1 import` | 25 / 14 | **both versions in active use** |
| `to_json` / `from_json` | 9 / 9 | portable |
| `to_jsonld` / `from_jsonld` | 4 / 1 | portable |
| `cast` / `cast_none_to_default` | 3 / 2 | portable |
| `get_raw` | 2 | obsolete (pattern A) |
| `LinkedBaseModelList` | 0 | no downstream use |
| `store_jsonld` | 0 | no downstream use |

## Why these patterns exist

Most of them are **workarounds for the shipped binding's hidden I/O**: plain
attribute access may perform a synchronous, un-batchable backend call inside
`__getattribute__`. Callers who cannot afford that, or cannot tell whether a
value is resolved, route around the getter. Under the descriptor binding -
where reads are batched, cached and return real objects - the reason for most
of these disappears.

### A. The resolved-or-IRI dance - **obsolete**

Application helpers repeat a shape equivalent to:

```python
def _load_first_relation(field_name):
    raw_value = (entity.get_raw(field_name)
                 if callable(getattr(entity, "get_raw", None))
                 else getattr(entity, field_name, None))
    if raw_value:
        return raw_value[0] if isinstance(raw_value, list) else raw_value
    relation_ids = (entity.get_iri_ref(field_name)
                    if callable(getattr(entity, "get_iri_ref", None))
                    else None)
    ...
```

It exists because the caller cannot ask "is this resolved?" without risking
resolution, and must therefore handle both representations. Under the new
binding the whole helper collapses to:

```python
values = entity.field          # real objects, batched and cached
return values[0] if values else None
```

Retires `get_raw` (2 sites) entirely.

### B. `try`/`except` around an attribute read - **obsolete**

Seen inside a published `opensemantic.*` package:

```python
try:
    char_iri = getattr(channel, "characteristic", None)
except (ValueError, ImportError):
    return None
```

Catching **`ImportError` from an attribute read** is the clearest symptom of the
problem: the getter resolves, which constructs a type, which may import. With
resolution moved out of the read path this guard has no reason to exist.

### C. Writing `__iris__` to fabricate a link - **obsolete, but must keep working**

Also inside a published `opensemantic.*` package:

```python
self.__iris__ = {"characteristic": characteristic_class.get_cls_iri()}
```

A stub object is given a link by writing the internal side-dict, because there
was no clean way to set a link to an IRI. Under the new binding that is simply:

```python
self.characteristic = characteristic_class.get_cls_iri()   # coerced to a link
```

Because this is **written**, not just read, a read-only `__iris__` shim would
silently drop the assignment. The compatibility layer therefore implements
`__iris__` as a read/write property.

### D. Hedging both representations - **simplifies**

```python
target = self.load_typed(obj.get_iri_ref("some_type") or obj.some_type, SomeType)
```

`... or ...` hedges: use the IRI if present, else whatever the attribute holds.
With one predictable representation this becomes a single expression.

### E. Comparing identity without fetching - **legitimate, keep**

```python
if module_iri in (subprocess.get_iri_ref("tool") or []):
    ...
```

Here the caller genuinely wants the IRI, not the object: resolving every related
entity only to compare identity would be wasteful even when batched. This is a
real primitive, not a workaround, so **`get_iri_ref` stays** with its current
name and return shape (`str | list[str] | None`).

### F. Capability probing - **obsolete**

```python
entity.get_raw(f) if callable(getattr(entity, "get_raw", None)) else ...
```

Defensive checks for whether the API exists at all. A stable base class removes
the need.

## The metaclass identity must move with the base class

Found by running a downstream test suite against a swapped binding rather than
by reading code. `opensemantic.characteristics.quantitative._static` does:

```python
from oold.model import LinkedBaseModelMetaClass as ModelMetaclass   # aliased!

class QuantityValueMetaclass(ModelMetaclass): ...
class QuantityValue(OswBaseModel, metaclass=QuantityValueMetaclass): ...
```

Downstream **imports and subclasses oold's metaclass**, aliased to a name that
makes it look like pydantic's. Replacing only `LinkedBaseModel` leaves
`LinkedBaseModelMetaClass` pointing at the old class, so `QuantityValue`'s
metaclass is no longer a subclass of its base's and the import dies with::

    TypeError: metaclass conflict: the metaclass of a derived class must be a
    (non-strict) subclass of the metaclasses of all its bases

The whole package tree fails to import - not a subtle behavioural drift but a
hard failure at collection time. So `LinkedBaseModelMetaClass` is **part of the
public API** and its identity has to be carried over together with the base
class, either by keeping the name bound to the new metaclass or by having the
new metaclass inherit from it.

Verified: after also rebinding the metaclass, the same suite imports cleanly and
passes.

## The type registry must be the same object

The same class of problem, found by enumerating every symbol downstream imports
from `oold`:

| imported from `oold.model` | sites |
|---|---:|
| `_types` | **7** |
| `LinkedBaseModel` | 2 |
| `LinkedBaseModelMetaClass` (aliased) | 1 |
| `BaseController` | 1 |

`_types` - the *private* registry - is imported more often than the base class
itself, and it is **written to**::

    from oold.model import _types
    _types[SomeClass.get_cls_iri()] = SomeClass

both in shipped package code and in examples. A replacement that keeps its own
registry dict does not see those entries, so polymorphic resolution silently
falls back to the declared target. Unlike the metaclass conflict this fails
**quietly**, which makes it the more dangerous of the two.

Fix: share the object, do not copy it - `use_type_registry(oold.model._types)`.

## How to solve both blockers

The rule the two findings share: **downstream imports `oold.model` internals by
name and mutates them, so the replacement must preserve names and object
identity, not merely behaviour.** Concretely:

1. **Name the new metaclass `LinkedBaseModelMetaClass`.** Downstream subclasses
   whatever that name resolves to, so pointing it at the new metaclass makes
   `class Derived(Base, metaclass=CustomMeta)` consistent by construction.
   Inheriting the *old* metaclass from the new one does not work - the derived
   metaclass must be a subclass of the base's, not the other way round.
2. **Bind the new registry to the existing `_types` dict** rather than creating
   one, so entries written through either name are visible to both.
3. **Keep `LinkedBaseModel` and `BaseController` as the exported names** for the
   new implementations.
4. Everything under `oold.backend.*` is untouched by the swap - the remaining
   downstream imports (`interface`, `document_store`, `auth`) need no action.

Both fixes are verified: with the metaclass rebound the previously failing suite
imports and passes, and with the registry shared a downstream registration
resolves through the new binding.

## Consequences for the replacement

**Must be preserved** (compatibility layer, `oold/experimental/compat.py`):

- `get_iri_ref(field)` -> `str | list[str] | None`, unchanged name and shape
- `__iris__`, readable **and assignable**
- `to_json`, `to_jsonld`, `from_json`, `from_jsonld`
- `cast`, `cast_none_to_default`, `get_cls_iri`, `export_schema`, `full_dict`
- both declaration styles: `json_schema_extra={"range": ...}` and bare `range=`
- **`LinkedBaseModelMetaClass`** - downstream subclasses it (see above)
- **`_types`** - the same dict object, downstream writes into it
- **pydantic v1 and v2**

**May be deprecated once downstream is updated**: `get_raw`, and the defensive
idioms in patterns A, B, C, F. They can be kept as thin shims and removed on a
later major version - none of them needs to survive in the new design on its
own merits.

**Not needed**: `LinkedBaseModelList` and `store_jsonld` have no downstream
callers, so the rich list operations and the store helper carry no
compatibility obligation (they remain available, but need not constrain the
design).

## Verification plan

Parity is asserted only when these pass unchanged against the new base:

1. the `oold-python` suite,
2. the test suites of the applications that call `get_iri_ref` directly and
   assert on its return shape,
3. a regenerated `opensemantic.core` diffed against the released package.

Status: step 2 has been run once for a suite that calls `get_iri_ref` and
asserts on its return shapes. Baseline **2 passed**; with the binding swapped
(base class *and* metaclass) **2 passed**, same result. The suite exercises a
live backend, so it covers construction, resolution and serialisation against
real data rather than fixtures.

[oold-python#107]: https://github.com/OO-LD/oold-python/issues/107
