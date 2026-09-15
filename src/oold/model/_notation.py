"""The link declaration notations proposed in issue #107 review comments.

1. ``OoldField()`` / ``OoldField(link=True)`` - no ``range=`` argument. The link
   target is inferred from the annotation, so the schema IRI is not repeated in
   Python. Note the trade-off: nothing then writes ``x-oold-range`` into the
   emitted schema, so pass ``range=`` where the schema is the artifact.
2. ``Link[T]`` / ``LinkList[T]`` as the **whole** annotation, e.g.
   ``employer: Link[Organization]`` or ``knows: LinkList["Person"]``. These are
   descriptor types, so a checker takes the ``__init__`` parameter and the
   assignment type from ``__set__`` and the attribute type from ``__get__``
   (PEP 681) - which is how one field carries both the resolved read type and
   the IRI-or-object write type. Optionality is declared in the parameter:
   ``Link[T]`` reads as ``T``, ``Link[T | None]`` as ``T | None``.

   They must be the whole annotation. Nested - ``list[Link[T]]`` or
   ``Optional[Link[T]]`` - a checker does not apply descriptor rules and the
   read type comes back wrong; use ``LinkList[T]`` and ``Link[T | None]``.
3. **Union forms** mixing literal, inline object and reference, e.g.
   ``location: Union[str, Location, None] = OoldField(link=True)``.

Everything reuses the descriptor machinery from
:mod:`oold.model._descriptor`; ``Link`` and ``LinkList`` are re-exported from
there rather than redefined, so there is one implementation, not two.
"""

from __future__ import annotations

import types
from typing import (
    Annotated,
    Any,
    ClassVar,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from pydantic import BaseModel, model_serializer

from oold.model._descriptor import (
    Link,
    LinkedBaseModel,
    LinkList,
    OoldField,
    _AutoLink,
    _extract_target,
    _LinkAnnotation,
    _register_class,
)

# Link and LinkList are re-exported: the notation module is the documented entry
# point for these declarations, and they are one implementation, not two.
__all__ = [
    "Link",
    "LinkList",
    "OoldField",
    "OoldModel",
]

T = TypeVar("T")

_LITERAL_TYPES = (str, int, float, bool, bytes)


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
        nonlocal marked, many
        while True:
            origin = get_origin(tp)
            if origin is Annotated:
                tp = get_args(tp)[0]
                continue
            # Link[X] / LinkList[X]: the annotation itself declares the link,
            # and LinkList carries the to-many-ness instead of a list wrapper
            if isinstance(origin, type) and issubclass(origin, _LinkAnnotation):
                args = get_args(tp)
                if not args:
                    break
                marked = True
                many = many or origin._many
                tp = args[0]
                continue
            break
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


class OoldModel(LinkedBaseModel):
    """Model base supporting the proposed link notations.

    Subclasses the binding rather than re-implementing it: it was a bare
    ``BaseModel``, so it was not a ``GenericLinkedBaseModel`` and could not be
    passed as a ``model_cls``. Resolution therefore always failed validation and
    only worked through ``_batch_resolve``'s fallback - which is to say, through
    the error path - and ``oold_query`` was a stub returning a tuple. It also
    carried byte-identical copies of ``__eq__``, ``__hash__``, ``get_iri`` and
    ``link_iris``.

    What stays here is the part that genuinely differs: union arms, where a bare
    string is a literal rather than a reference.
    """

    __link_literals__: ClassVar[dict[str, list[Any]]] = {}

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
            if not (explicit_range or flagged or marked):
                continue
            if explicit_range and not isinstance(target, type):
                target = explicit_range
            # carry the same promises the binding computes, so Link[T] is
            # mandatory here too and x-oold-required-iri is enforced
            _, _, optional = _extract_target(field.annotation)
            descr = _AutoLink(
                name,
                target,
                many=many,
                optional=optional,
                required_iri=bool(extra.get("x-oold-required-iri")),
            )
            setattr(cls, name, descr)
            links[name] = descr
            if lits:
                literals[name] = lits
        cls.__link_fields__ = links
        cls.__link_literals__ = literals
        # Register the way the binding does - including the inherited-IRI
        # guard - rather than writing the type default straight in, which let a
        # subclass that only narrows a field replace its parent in the registry.
        _register_class(cls)

    def _set_link(self, name: str, value: Any) -> None:
        # union arms: a bare string stays a literal when the field also
        # declares a literal arm; a reference then arrives as {"@id": ...}
        arms = type(self).__link_literals__.get(name)
        if arms and isinstance(value, str):
            object.__setattr__(self, name, value)
            self._links.pop(name, None)
            return
        type(self).__link_fields__[name].set_value(self, self._coerce(value))

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

    @model_serializer(mode="wrap")
    def _serialize_links(self, handler: Any) -> dict[str, Any]:
        d = handler(self)
        literals = type(self).__link_literals__
        for name in type(self).__link_fields__:
            stored = self._links.get(name)
            if stored is None and name not in self._links:
                # Never set as a link. A literal arm may have taken the value,
                # in which case the plain field already serialised it; keep it.
                # Otherwise the field is unset and contributes nothing - drop
                # the [] the descriptor hands back so it stays out of payloads.
                # handler() has already read the descriptor, which caches its
                # [] into __dict__, so test the emitted value rather than the
                # instance: a literal arm leaves a real value here.
                if d.get(name) in (None, [], {}):
                    d.pop(name, None)
                continue
            # A field that also accepts a literal cannot emit a reference as a
            # bare IRI: on re-read the string would be indistinguishable from
            # text. JSON-LD spells the unambiguous form {"@id": ...}.
            boxed = bool(literals.get(name))
            emitted = _emit(stored, boxed)
            # An explicit empty list is kept - it round-trips as [] and is not
            # the same statement as "unset", which is dropped above.
            if emitted is None:
                d.pop(name, None)
            else:
                d[name] = emitted
        return d
