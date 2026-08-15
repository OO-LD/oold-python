"""Prototype: explicit ``Ref[T]`` graph-object binding.

This is the proof-of-concept for the binding recommendation in
``docs/design/graph-object-binding.md``. It demonstrates that OO-LD's
object-graph binding (a string-IRI ``x-oold-range`` field that can be built
from an object *or* an IRI, resolves lazily through a backend, and serialises
back to an IRI) can be expressed **without** any of the machinery the shipped
``oold.model`` relies on:

- no metaclass and no ``__getattribute__`` / ``__setattr__`` override on the
  model,
- no process-wide ``pydantic.fields.FieldInfo`` monkeypatch,
- no parallel ``__iris__`` side-dict duplicating field state.

Instead a single generic type ``Ref[T]`` carries the reference. Pydantic v2
handles validation and serialisation through the type's own core schema, so
only the reference fields pay any cost; plain fields keep native pydantic
attribute access. Resolution reuses the existing backend layer
(``oold.backend.interface`` + ``oold.backend.document_store``) unchanged.

The module deliberately imports only ``oold.backend.interface`` (which does not
import ``oold.model``), so importing this prototype does not patch
``FieldInfo``. See ``tests/test_ref_binding.py``.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Generic,
    List,
    Optional,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic_core import core_schema

from oold.backend.interface import GetResolverParam, get_resolver

T = TypeVar("T")


class OoldModel(BaseModel):
    """Minimal experimental base: JSON round-trip + IRI identity, no metaclass.

    Range fields are declared with the :class:`Ref` type, e.g.
    ``b: Optional[Ref[Bar]] = None``. Everything else is plain pydantic.
    """

    def get_iri(self) -> Optional[str]:
        """Return the object's IRI (defaults to its ``id`` field)."""
        return getattr(self, "id", None)

    def to_json(self, exclude_none: bool = True) -> dict:
        """Serialise to a plain dict; :class:`Ref` fields collapse to IRIs."""
        return self.model_dump(exclude_none=exclude_none)

    @classmethod
    def ld_context(cls) -> dict:
        """JSON-LD context for :meth:`to_jsonld`. Override per model.

        Reference fields must map to ``{"@type": "@id"}`` so that a JSON-LD
        processor treats the serialised IRI string as a node reference rather
        than a literal.
        """
        return {"id": "@id", "type": "@type"}

    def to_jsonld(self) -> dict:
        """Return a compact JSON-LD document; ``Ref`` fields are IRI nodes."""
        return {"@context": self.ld_context(), **self.to_json()}

    @classmethod
    def from_dict(cls, d: dict) -> "OoldModel":
        """Construct from a stored dict, ignoring non-field keys (@context...)."""
        fields = getattr(cls, "model_fields", {})
        return cls(**{k: v for k, v in d.items() if k in fields})


def _construct(target: Optional[type], d: Any) -> Any:
    if target is None:
        return d
    if hasattr(target, "from_dict"):
        return target.from_dict(d)
    return target(**d)


def _strip_optional(tp: Any) -> Any:
    """Return the non-None arm of Optional[X] / Union[X, None], else tp."""
    if get_origin(tp) is Union:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _ref_core_schema(target: Optional[type]) -> core_schema.CoreSchema:
    """Pydantic v2 core schema shared by ``Ref[T]`` and ``OoldRange``.

    Validation coerces an IRI string / dict / model / existing ``Ref`` into a
    ``Ref``; serialisation emits the IRI. The schema fully replaces the target's
    own schema, so the runtime value is a ``Ref`` even when the *declared* type
    is the target (the transparent ``Linked[T]`` form).
    """

    def validate(value: Any) -> Optional["Ref"]:
        if value is None:
            return None
        if isinstance(value, Ref):
            if value._target is None:
                value._target = target
            return value
        if isinstance(value, str):
            return Ref(iri=value, target=target)
        if isinstance(value, BaseModel):
            return Ref(obj=value, target=target)
        if isinstance(value, dict):
            return Ref(obj=_construct(target, value), target=target)
        raise ValueError(f"Cannot coerce {value!r} into Ref[{target}]")

    def serialize(ref: Optional["Ref"]) -> Optional[str]:
        return None if ref is None else ref.iri

    return core_schema.no_info_plain_validator_function(
        validate,
        serialization=core_schema.plain_serializer_function_ser_schema(
            serialize, when_used="always"
        ),
    )


class Ref(Generic[T]):
    """A typed reference to a linked object, by IRI or by value.

    A ``Ref`` holds either an unresolved ``iri`` or a resolved ``_obj`` (or
    both once resolved). It resolves lazily and explicitly:

    - ``ref.resolve()`` returns the target object, fetching it through the
      registered backend on first use and caching it,
    - attribute access delegates transparently (``foo.b.name`` resolves ``b``
      then reads ``name``) - but, unlike the shipped model, the magic lives on
      the reference object, not on every model attribute access.

    Serialisation always emits the IRI, so an object graph round-trips to
    IRI-linked JSON / JSON-LD.
    """

    __slots__ = ("iri", "_obj", "_target")

    def __init__(
        self,
        iri: Optional[str] = None,
        obj: Optional[T] = None,
        target: Optional[type] = None,
    ):
        self._obj = obj
        self._target = target
        if iri is None and obj is not None and hasattr(obj, "get_iri"):
            iri = obj.get_iri()
        self.iri = iri

    # resolution

    @property
    def resolved(self) -> bool:
        return self._obj is not None

    def resolve(self) -> Optional[T]:
        """Return the target object, resolving via the backend on first use."""
        if self._obj is None and self.iri is not None:
            resolver = get_resolver(GetResolverParam(iri=self.iri)).resolver
            fetched = resolver.resolve_iris([self.iri]).get(self.iri)
            if fetched is None:
                raise KeyError(f"Could not resolve reference {self.iri!r}")
            self._obj = _construct(self._target, fetched)
        return self._obj

    async def aresolve(self) -> Optional[T]:
        """Async resolution hook.

        The shipped binding cannot express this at all - resolution is buried
        inside synchronous ``__getattribute__``. Here it is an ordinary method,
        so an async backend can be awaited. The in-repo backends are sync, so
        this simply defers to :meth:`resolve`.
        """
        return self.resolve()

    def __getattr__(self, name: str) -> Any:
        # Only called for names not found normally (Ref uses __slots__), so it
        # never shadows iri/_obj/resolve. Transparent, explicit delegation.
        obj = self.resolve()
        return getattr(obj, name)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Ref):
            return self.iri == other.iri
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.iri)

    def __repr__(self) -> str:
        return f"Ref(iri={self.iri!r}, resolved={self.resolved})"

    # pydantic v2 integration

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        args = get_args(source_type)
        target = args[0] if args else None
        return _ref_core_schema(target)


class OoldRange:
    """Annotated-metadata form of the binding, for transparent static typing.

    Declare a link field with the target type directly and attach this marker:
    ``knows: list[Annotated[Person, OoldRange()]]`` - or, equivalently, the
    :data:`Linked` alias, ``knows: list[Linked[Person]]``.

    A type checker sees the field as ``Person`` (per PEP 593, ``Annotated[X, ...]``
    is ``X`` for typing), so ``foo.knows[0].name`` autocompletes and type-checks
    like the shipped model. At runtime the value is still a lazy :class:`Ref`;
    the target is read from the annotated type, not passed in.
    """

    def __get_pydantic_core_schema__(
        self, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return _ref_core_schema(_strip_optional(source))


if TYPE_CHECKING:
    _LinkedT = TypeVar("_LinkedT")
    # For type checkers, Linked[X] is Annotated[X, ...] which reads as X.
    Linked = Annotated[_LinkedT, "oold-linked"]
else:

    class _LinkedAlias:
        """Runtime side: ``Linked[X]`` becomes ``Annotated[X, OoldRange()]``."""

        def __getitem__(self, item: Any) -> Any:
            return Annotated[item, OoldRange()]

    Linked = _LinkedAlias()


# Demo models mirroring the README Foo/Bar example.


class Bar(OoldModel):
    id: str
    prop1: Optional[str] = None


class Foo(OoldModel):
    id: str
    literal: Optional[str] = None
    b: Optional[Ref[Bar]] = None
    b2: Optional[List[Ref[Bar]]] = None

    @classmethod
    def ld_context(cls) -> dict:
        return {
            "ex": "https://example.org/",
            "id": "@id",
            "type": "@type",
            "literal": "ex:literal",
            "b": {"@id": "ex:hasB", "@type": "@id"},
            "b2": {"@id": "ex:hasB2", "@type": "@id"},
        }


class Person(OoldModel):
    """Transparent form: ``knows`` is declared as ``list[Person]``.

    A type checker sees ``person.knows[0]`` as ``Person`` (so ``.name``
    autocompletes), while at runtime each item is a lazy :class:`Ref[Person]`
    that resolves through the backend and serialises back to an IRI.
    """

    id: str
    name: Optional[str] = None
    knows: Optional[List[Linked["Person"]]] = None


Person.model_rebuild()


def demo() -> None:  # pragma: no cover - manual smoke run
    from oold.backend.document_store import SimpleDictDocumentStore
    from oold.backend.interface import SetResolverParam, set_resolver

    store = SimpleDictDocumentStore()
    store.store_json_dicts({"ex:b": {"id": "ex:b", "prop1": "resolved-prop1"}})
    set_resolver(SetResolverParam(iri="ex", resolver=store))

    # Build by object
    f1 = Foo(id="ex:f", literal="x", b=Bar(id="ex:b", prop1="inline"))
    print("by-object dump:", f1.to_json())
    print("by-object b.prop1:", f1.b.prop1)

    # Build by IRI (lazy resolution through the backend)
    f2 = Foo(id="ex:f", b="ex:b")
    print("by-iri dump:", f2.to_json())
    print("by-iri resolved prop1:", f2.b.prop1)


if __name__ == "__main__":  # pragma: no cover
    demo()
