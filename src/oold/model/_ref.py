"""Typed reference values for the graph-object binding.

A :class:`Ref` holds either an unresolved IRI or a resolved object. The
descriptor binding stores links as ``Ref`` instances, which is what lets a
link be inspected (``get_iri_ref``) without triggering resolution, resolved
in batches, and serialised back to an IRI.
"""

from __future__ import annotations

from typing import (
    Any,
    Generic,
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

    def get_iri(self) -> str | None:
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
    def from_dict(cls, d: dict) -> OoldModel:
        """Construct from a stored dict, ignoring non-field keys (@context...)."""
        fields = getattr(cls, "model_fields", {})
        return cls(**{k: v for k, v in d.items() if k in fields})


def _construct(target: type | None, d: Any) -> Any:
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


def _ref_core_schema(target: type | None) -> core_schema.CoreSchema:
    """Pydantic v2 core schema shared by ``Ref[T]`` and ``OoldRange``.

    Validation coerces an IRI string / dict / model / existing ``Ref`` into a
    ``Ref``; serialisation emits the IRI. The schema fully replaces the target's
    own schema, so the runtime value is a ``Ref`` even when the *declared* type
    is the target (the transparent ``Linked[T]`` form).
    """

    def validate(value: Any) -> Ref | None:
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

    def serialize(ref: Ref | None) -> str | None:
        return None if ref is None else ref.iri

    return core_schema.no_info_plain_validator_function(
        validate,
        serialization=core_schema.plain_serializer_function_ser_schema(serialize, when_used="always"),
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

    __slots__ = ("_obj", "_target", "iri")

    def __init__(
        self,
        iri: str | None = None,
        obj: T | None = None,
        target: type | None = None,
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

    def resolve(self) -> T | None:
        """Return the target object, resolving via the backend on first use."""
        if self._obj is None and self.iri is not None:
            resolver = get_resolver(GetResolverParam(iri=self.iri)).resolver
            fetched = resolver.resolve_iris([self.iri]).get(self.iri)
            if fetched is None:
                raise KeyError(f"Could not resolve reference {self.iri!r}")
            self._obj = _construct(self._target, fetched)
        return self._obj

    async def aresolve(self) -> T | None:
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
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        args = get_args(source_type)
        target = args[0] if args else None
        return _ref_core_schema(target)
