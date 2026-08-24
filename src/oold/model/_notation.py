"""Prototype of the notations proposed in issue #107 review comments.

Three proposals are implemented and exercised here:

1. ``OoldField()`` / ``OoldField(link=True)`` - no ``range=`` argument. The link
   target is inferred from the annotation, so the schema IRI is not repeated in
   Python. ``OoldField()`` with no arguments at all is equivalent for a
   non-literal target.
2. ``Link[T]`` **inside** the annotation, e.g.
   ``employer: Optional[Link[Organization]]`` or
   ``friends: Optional[List[Link["Person"]]]``. ``Link[T]`` is
   ``Annotated[T, LinkMarker()]``, so a type checker reads it as ``T`` - and,
   unlike the rejected ``Annotated``-over-``Ref`` form, the runtime value really
   *is* a ``T``, because the descriptor returns the resolved object.
3. **Union forms** mixing literal, inline object and reference, e.g.
   ``location: Union[str, Location, Link[Location]]``.

Everything reuses the descriptor machinery from
:mod:`oold.model._descriptor`.
"""

from __future__ import annotations

import types
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_serializer

from oold.model._descriptor import (
    _TYPE_REGISTRY,
    LinkedQueryMeta,
    OoldExtra,
    _AutoLink,
)

T = TypeVar("T")

_LITERAL_TYPES = (str, int, float, bool, bytes)


class LinkMarker:
    """``Annotated`` metadata marking a property as an IRI-valued link."""

    __slots__ = ("required_iri",)

    def __init__(self, required_iri: bool = False):
        self.required_iri = required_iri

    def __repr__(self) -> str:
        return f"LinkMarker(required_iri={self.required_iri})"


if TYPE_CHECKING:
    # For type checkers Link[X] is Annotated[X, ...], which reads as X.
    Link = Annotated[T, "oold-link"]
else:

    class _LinkAlias:
        def __getitem__(self, item: Any) -> Any:
            return Annotated[item, LinkMarker()]

    Link = _LinkAlias()


def OoldField(
    *,
    link: bool | None = None,
    range: str | None = None,
    required_iri: bool | None = None,
    **kwargs: Any,
) -> Any:
    """``Field`` wrapper marking a property as a link.

    ``range`` is optional: when omitted the target is taken from the
    annotation. ``OoldField()`` therefore suffices in the common case.
    """
    extra: dict[str, Any] = {}
    if range is not None:
        extra = dict(OoldExtra(range=range, required_iri=required_iri))
    else:
        extra["x-oold-link"] = True if link is None else bool(link)
        if required_iri is not None:
            extra["x-oold-required-iri"] = required_iri
    # Link values are routed out of the payload before pydantic validates, so a
    # link field must not be required at the pydantic level. This also makes the
    # bare OoldField() form work with no arguments at all.
    kwargs.setdefault("default", None)
    return Field(**kwargs, json_schema_extra=extra)


_UNION_ORIGINS = {Union}
if hasattr(types, "UnionType"):  # PEP 604: X | None
    _UNION_ORIGINS.add(types.UnionType)


def _unwrap(annotation: Any) -> tuple[Any, bool, bool, list[Any]]:
    """Return (target, many, has_link_marker, literal_arms) for an annotation.

    Understands ``Optional[...]``, ``List[...]``, ``Annotated[...]`` and unions
    mixing a literal arm, an inline-object arm and a ``Link[...]`` arm.
    """
    many = False
    marked = False
    literals: list[Any] = []
    target = annotation

    def strip(tp: Any) -> Any:
        nonlocal marked
        while get_origin(tp) is Annotated:
            args = get_args(tp)
            if any(isinstance(m, LinkMarker) for m in args[1:]):
                marked = True
            tp = args[0]
        return tp

    changed = True
    while changed:
        changed = False
        target = strip(target)
        origin = get_origin(target)
        if origin in _UNION_ORIGINS:
            arms = [a for a in get_args(target) if a is not type(None)]
            model_arms, other = [], []
            for arm in arms:
                bare = strip(arm)
                if isinstance(bare, type) and issubclass(bare, BaseModel):
                    model_arms.append(bare)
                elif bare in _LITERAL_TYPES:
                    other.append(bare)
                else:
                    model_arms.append(bare)
            literals.extend(other)
            if len(model_arms) >= 1:
                target, changed = model_arms[0], True
            elif other:
                target, changed = other[0], True
        elif origin in (list, list):
            args = get_args(target)
            if args:
                target, many, changed = strip(args[0]), True, True
    return target, many, marked, literals


def _emit_one(ref: Any, boxed: bool) -> Any:
    """Serialise a single stored reference.

    ``boxed`` is set when the field also accepts a literal, in which case a
    reference must be written as ``{"@id": ...}`` so that re-reading it cannot
    be confused with text. A value without an IRI has no reference to emit, so
    it is written inline - a blank node.
    """
    if ref is None:
        return None
    iri = getattr(ref, "iri", None)
    if iri:
        return {"@id": iri} if boxed else iri
    obj = getattr(ref, "_obj", None)
    if obj is None:
        return None
    return obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else obj


def _emit(stored: Any, boxed: bool) -> Any:
    if isinstance(stored, list):
        out = [_emit_one(r, boxed) for r in stored]
        return [v for v in out if v is not None]
    return _emit_one(stored, boxed)


class OoldModel(BaseModel, metaclass=LinkedQueryMeta):
    """Model base supporting the proposed link notations."""

    model_config = ConfigDict(ignored_types=(_AutoLink,))

    _links: dict[str, Any] = PrivateAttr(default_factory=dict)
    __link_fields__: ClassVar[dict[str, _AutoLink]] = {}
    __link_literals__: ClassVar[dict[str, list[Any]]] = {}

    @classmethod
    def oold_query(cls, item: Any) -> Any:
        return ("query", cls.__name__, item)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        links: dict[str, _AutoLink] = dict(getattr(cls, "__link_fields__", {}))
        literals: dict[str, list[Any]] = dict(getattr(cls, "__link_literals__", {}))
        for name, field in cls.model_fields.items():
            extra = field.json_schema_extra
            extra = extra if isinstance(extra, dict) else {}
            explicit_range = extra.get("x-oold-range") or extra.get("range")
            flagged = bool(extra.get("x-oold-link"))
            target, many, marked, lits = _unwrap(field.annotation)
            # a top-level Annotated marker is moved into field.metadata by pydantic
            if any(isinstance(m, LinkMarker) for m in getattr(field, "metadata", [])):
                marked = True
            if not (explicit_range or flagged or marked):
                continue
            if explicit_range and not isinstance(target, type):
                target = explicit_range
            descr = _AutoLink(name, target, many)
            setattr(cls, name, descr)
            links[name] = descr
            if lits:
                literals[name] = lits
        cls.__link_fields__ = links
        cls.__link_literals__ = literals
        type_field = cls.model_fields.get("type")
        if type_field is not None and isinstance(type_field.default, str):
            _TYPE_REGISTRY[type_field.default] = cls

    def __init__(self, **data: Any) -> None:
        lf = type(self).__link_fields__
        lits = type(self).__link_literals__
        link_data = {k: data.pop(k) for k in list(data) if k in lf}
        super().__init__(**data)
        for key, value in link_data.items():
            # union arms: a bare string stays a literal when the field also
            # declares a literal arm; a reference then arrives as {"@id": ...}
            arms = lits.get(key)
            if arms and isinstance(value, str):
                object.__setattr__(self, key, value)
                self._links.pop(key, None)
                continue
            lf[key].set_value(self, self._coerce(value))

    @staticmethod
    def _coerce(value: Any) -> Any:
        def one(v: Any) -> Any:
            if isinstance(v, dict) and set(v) == {"@id"}:
                return v["@id"]  # pure reference object
            return v

        if isinstance(value, list):
            return [one(v) for v in value]
        return one(value)

    def __setattr__(self, name: str, value: Any) -> None:
        descr = type(self).__link_fields__.get(name)
        if descr is not None:
            arms = type(self).__link_literals__.get(name)
            if arms and isinstance(value, str):
                object.__setattr__(self, name, value)
                self._links.pop(name, None)
                return
            descr.set_value(self, self._coerce(value))
        else:
            super().__setattr__(name, value)

    def get_iri(self) -> str | None:
        return getattr(self, "id", None)

    def link_iris(self, name: str) -> Any:
        return type(self).__link_fields__[name].iris(self)

    @model_serializer(mode="wrap")
    def _serialize_links(self, handler: Any) -> dict[str, Any]:
        d = handler(self)
        literals = type(self).__link_literals__
        for name, descr in type(self).__link_fields__.items():
            stored = self._links.get(name)
            if stored is None and name not in self._links:
                # never set as a link: a literal arm may have taken the value,
                # in which case the plain pydantic field already serialised it
                continue
            # A field that also accepts a literal cannot emit a reference as a
            # bare IRI: on re-read the string would be indistinguishable from
            # text. JSON-LD spells the unambiguous form {"@id": ...}.
            boxed = bool(literals.get(name))
            emitted = _emit(stored, boxed)
            if emitted is None and descr.many:
                emitted = []
            if emitted in (None, []) and not descr.many:
                d.pop(name, None)
            else:
                d[name] = emitted
        return d
