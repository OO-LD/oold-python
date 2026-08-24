"""Prototype: auto-installed descriptors, with NO declaration syntax change.

This combines the advantages of the shipped binding and the explicit descriptor
form. Models are declared exactly as they are today - standard annotations,
including plain ``List[...]`` for to-many links:

    class Person(AutoLinkedModel):
        id: str
        name: Optional[str] = None
        knows: Optional[List["Person"]] = Field(
            None, json_schema_extra={"x-oold-range": "Person"}
        )

No wrapper types, no unannotated assignments; the generated code that
``datamodel-code-generator`` already emits keeps working unchanged.

After pydantic finishes building the class, ``__pydantic_init_subclass__`` scans
``model_fields`` for a ``x-oold-range`` (or legacy ``range``) annotation and
**installs a data descriptor** for each such field. Because a data descriptor
takes precedence over an instance ``__dict__`` entry during normal attribute
lookup, the descriptor handles link reads while every other field keeps native
pydantic access. The "is this a range field?" test is therefore performed by the
interpreter's C-level attribute lookup instead of a Python ``__getattribute__``,
so plain fields cost nothing.

Semantics match the shipped binding: reading a link returns the **real**
resolved object (``isinstance`` holds), resolution is lazy, and references
serialise back to IRIs. Resolution is additionally **batched** - a list resolves
in one backend call.
"""

from __future__ import annotations

import types
from collections import defaultdict
from typing import (
    Any,
    ClassVar,
    Generic,
    TypeVar,
    Union,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_serializer
from pydantic._internal._model_construction import ModelMetaclass

from oold.backend.interface import (
    Condition,
    GetResolverParam,
    apply_operator,
    get_resolver,
)
from oold.model._compat import LinkedApiMixin
from oold.model._ref import Ref, _construct

T = TypeVar("T")


class OoldExtraModel(BaseModel):
    """Validated model behind :class:`OoldExtra` (constraints live here)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    range: str = Field(alias="x-oold-range", min_length=1)
    required_iri: bool | None = Field(None, alias="x-oold-required-iri")


class OoldExtra(dict[str, Any]):
    """Typed, pydantic-validated replacement for a raw ``json_schema_extra`` dict.

    Must subclass ``dict``: pydantic merges ``json_schema_extra`` into the JSON
    schema only via ``isinstance(json_schema_extra, dict)``, so a plain
    ``BaseModel`` would be silently dropped from the schema.

    Validation is delegated to :class:`OoldExtraModel`, so real
    ``ValidationError`` s are raised at declaration time, while typed properties
    give checked read access instead of stringly-typed ``extra["x-oold-range"]``.
    """

    def __init__(
        self,
        *,
        range: str,
        required_iri: bool | None = None,
        **vendor: Any,
    ) -> None:
        data: dict[str, Any] = {"x-oold-range": range}
        if required_iri is not None:
            data["x-oold-required-iri"] = required_iri
        data.update(vendor)
        # model_validate (not kwargs) keeps aliased names out of the call
        # signature, which otherwise confuses type checkers.
        model = OoldExtraModel.model_validate(data)
        object.__setattr__(self, "_model", model)
        super().__init__(model.model_dump(by_alias=True, exclude_none=True))

    @property
    def model(self) -> OoldExtraModel:
        return self._model  # type: ignore[attr-defined]

    @property
    def range(self) -> str:
        return self.model.range

    @property
    def required_iri(self) -> bool | None:
        return self.model.required_iri


def OoldField(
    *,
    range: str | None = None,
    link: bool | None = None,
    required_iri: bool | None = None,
    **kwargs: Any,
) -> Any:
    """``Field`` wrapper marking a property as a link.

    ``range`` is optional: when omitted the link target is taken from the
    annotation, so ``OoldField()`` on its own is enough for the common case.
    """
    if range is not None:
        extra: dict[str, Any] = dict(OoldExtra(range=range, required_iri=required_iri))
    else:
        extra = {"x-oold-link": True if link is None else bool(link)}
        if required_iri is not None:
            extra["x-oold-required-iri"] = required_iri
    # Link values are routed out of the payload before pydantic validates, so a
    # link field must not be required at the pydantic level. This also makes the
    # bare OoldField() form work with no arguments at all.
    kwargs.setdefault("default", None)
    return Field(**kwargs, json_schema_extra=extra)


class FieldProxy:
    """Class-level field handle enabling ``Person.name == "John"``."""

    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other: Any) -> Any:  # type: ignore[override]
        return Condition(field=self.name, operator="eq", value=other)

    def __ne__(self, other: Any) -> Any:  # type: ignore[override]
        return Condition(field=self.name, operator="ne", value=other)

    def __lt__(self, other: Any) -> Any:
        return Condition(field=self.name, operator="lt", value=other)

    def __le__(self, other: Any) -> Any:
        return Condition(field=self.name, operator="le", value=other)

    def __gt__(self, other: Any) -> Any:
        return Condition(field=self.name, operator="gt", value=other)

    def __ge__(self, other: Any) -> Any:
        return Condition(field=self.name, operator="ge", value=other)

    def __hash__(self) -> int:
        return id(self)


class LinkedQueryMeta(ModelMetaclass):
    """Metaclass providing the query DSL without touching attribute reads.

    Uses ``__getattr__`` (a fallback, invoked only when normal lookup *fails*)
    rather than ``__getattribute__`` (invoked on *every* access). Pydantic v2
    removes field names from the class namespace, so ``Person.name`` fails
    naturally and lands here at no cost to any other attribute access.
    """

    def __getattr__(cls, name: str) -> Any:
        # Never call getattr(cls, ...) here: cls.model_fields is a property
        # that itself calls getattr, which would recurse until the stack blows.
        if name.startswith("_"):
            raise AttributeError(name)
        for klass in cls.__mro__:
            fields = klass.__dict__.get("__pydantic_fields__")
            if fields and name in fields:
                return FieldProxy(name)
        raise AttributeError(name)

    def __getitem__(cls, item: Any) -> Any:
        return cls.oold_query(item)


_UNION_ORIGINS = {Union}
if hasattr(types, "UnionType"):  # PEP 604: X | None
    _UNION_ORIGINS.add(types.UnionType)


def _extract_target(annotation: Any) -> tuple[Any, bool]:
    """Return (target_type, is_many) for an annotation like Optional[List[X]]."""
    many = False
    target = annotation
    changed = True
    while changed:
        changed = False
        origin = get_origin(target)
        if origin in _UNION_ORIGINS:
            args = [a for a in get_args(target) if a is not type(None)]
            if len(args) == 1:
                target, changed = args[0], True
        elif origin is list:
            args = get_args(target)
            if args:
                target, many, changed = args[0], True, True
    return target, many


_TYPE_REGISTRY: dict[str, type] = {}
"""Maps a ``type`` field default (the class IRI) to its model class.

Identity matters, not just contents. Downstream imports the shipped registry
directly and **writes into it**::

    from oold.model import _types
    _types[SomeClass.get_cls_iri()] = SomeClass

so on integration this must *be* ``oold.model._types``, not a second dict -
otherwise those registrations are invisible here and polymorphic resolution
silently falls back to the declared target. Use :func:`use_type_registry`.
"""


def use_type_registry(registry: dict) -> None:
    """Adopt an existing registry mapping, sharing its identity.

    Call with ``oold.model._types`` when this binding replaces the shipped one,
    so registrations made through either name are seen by both.
    """
    global _TYPE_REGISTRY
    _TYPE_REGISTRY = registry


def _resolve_cls(data: dict[str, Any], target: Any) -> Any:
    """Pick the most specific class for a document, by its type IRI."""
    type_iri = data.get("type")
    if isinstance(type_iri, list):
        type_iri = type_iri[0] if type_iri else None
    if isinstance(type_iri, str):
        found = _TYPE_REGISTRY.get(type_iri)
        if found is not None:
            return found
    return target


class LinkResultList(list[Any]):
    """List returned by a to-many link, with IRI lookup, filtering, projection."""

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, str):
            for item in self:
                if item is not None and getattr(item, "id", None) == index:
                    return item
            raise KeyError(index)
        if isinstance(index, Condition):
            return LinkResultList(
                item
                for item in self
                if item is not None and apply_operator(index.operator, getattr(item, index.field, None), index.value)
            )
        return list.__getitem__(self, index)

    def __getattr__(self, name: str) -> Any:
        # Only invoked when normal lookup fails, so list methods are unaffected.
        if name.startswith("_"):
            raise AttributeError(name)
        out = LinkResultList()
        for item in self:
            if item is None:
                continue
            value = getattr(item, name)
            if isinstance(value, list):
                out.extend(value)
            else:
                out.append(value)
        return out


def _batch_resolve(refs: list[Ref | None], target: Any) -> list[Any]:
    """Resolve all unresolved refs, one backend call per resolver prefix."""
    pending = [r for r in refs if r is not None and r._obj is None and r.iri]
    groups: dict[str, list[Ref]] = defaultdict(list)
    for r in pending:
        groups[r.iri.split(":")[0]].append(r)
    for group in groups.values():
        iris = [r.iri for r in group]
        resolver = get_resolver(GetResolverParam(iri=iris[0])).resolver
        fetched = resolver.resolve_iris(iris)
        for r in group:
            d = fetched.get(r.iri)
            # dispatch on the document's type IRI so a stored subclass
            # resolves to the subclass, not merely to the declared target
            r._obj = _construct(_resolve_cls(d, target), d) if d is not None else None
    return [None if r is None else r._obj for r in refs]


def _to_ref(value: Any, target: Any) -> Ref | None:
    if value is None:
        return None
    if isinstance(value, Ref):
        if value._target is None:
            value._target = target
        return value
    if isinstance(value, str):
        return Ref(iri=value, target=target)
    if isinstance(value, dict):
        # construct through the model so the linked object is validated
        cls = _resolve_cls(value, target)
        if cls is None:
            raise ValueError(f"Cannot construct link from {value!r}: unknown target")
        return Ref(obj=_construct(cls, value), target=target)
    return Ref(obj=value, target=target)


class _AutoLink:
    """Data descriptor backing a link field.

    Installed automatically for annotated ``x-oold-range`` fields (implicit
    form), or declared directly in a class body via :class:`Link` /
    :class:`LinkList` (explicit form). Both forms share this implementation, so
    runtime behaviour is identical.
    """

    def __init__(self, name: str | None = None, target: Any = None, many: bool = False):
        self.name = name
        self.target = target
        self.many = many
        self.owner: Any = None

    def __set_name__(self, owner: type, name: str) -> None:
        # Only relevant for the explicit form (declared in the class body).
        if self.name is None:
            self.name = name
        self.owner = owner

    def _target_cls(self, owner: Any) -> Any:
        cached = self.__dict__.get("_resolved_target")
        if cached is not None:
            return cached
        target = self.target
        if target is None:
            # Explicit form declared as LinkList["Person"]() with no argument:
            # recover the type argument from __orig_class__, which typing sets
            # on the instance after __init__ (also inside a class body).
            orig = self.__dict__.get("__orig_class__")
            if orig is not None:
                args = get_args(orig)
                if args:
                    target = args[0]
        if hasattr(target, "__forward_arg__"):  # ForwardRef("Person")
            target = target.__forward_arg__
        if isinstance(target, str):
            import sys

            module = sys.modules.get(getattr(owner or self.owner, "__module__", ""), None)
            target = getattr(module, target, None) if module else None
        if target is not None:
            self.__dict__["_resolved_target"] = target
        return target

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            # Class access returns the descriptor, so Person.knows == "x" can
            # build a Condition without any metaclass involvement.
            return self
        stored = obj._links.get(self.name)
        target = self._target_cls(objtype or type(obj))
        if self.many:
            result = LinkResultList(_batch_resolve(stored, target)) if stored else LinkResultList()
        elif stored is None:
            result = None
        else:
            result = _batch_resolve([stored], target)[0]
        # Store the resolved value in the instance __dict__. This descriptor is
        # deliberately NON-data (no __set__), so from now on normal attribute
        # lookup finds the instance dict first and never calls back into Python:
        # warm link reads run at native speed (the functools.cached_property
        # pattern). Writes are still intercepted, by LinkedModel.__setattr__.
        obj.__dict__[self.name] = result
        return result

    def set_value(self, obj: Any, value: Any) -> None:
        target = self._target_cls(type(obj))
        if self.many:
            obj._links[self.name] = [] if value is None else [_to_ref(v, target) for v in value]
        else:
            obj._links[self.name] = _to_ref(value, target)
        obj.__dict__.pop(self.name, None)  # invalidate the cached read

    def __eq__(self, other: Any) -> Any:  # type: ignore[override]
        return Condition(field=self.name, operator="eq", value=other)

    def __ne__(self, other: Any) -> Any:  # type: ignore[override]
        return Condition(field=self.name, operator="ne", value=other)

    def __hash__(self) -> int:
        return id(self)

    def iris(self, obj: Any) -> Any:
        stored = obj._links.get(self.name)
        if self.many:
            return [r.iri for r in (stored or []) if r is not None and r.iri]
        return stored.iri if stored is not None else None


class Link(_AutoLink, Generic[T]):
    """Explicit to-one link descriptor: ``employer = Link(Organization)``."""

    def __init__(self, target: type[T] | str | None = None):
        super().__init__(name=None, target=target, many=False)

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> Link[T]: ...

    @overload
    def __get__(self, obj: object, objtype: Any = None) -> T | None: ...

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return _AutoLink.__get__(self, obj, objtype)


class LinkList(_AutoLink, Generic[T]):
    """Explicit to-many link descriptor: ``knows = LinkList["Person"]()``."""

    def __init__(self, target: type[T] | str | None = None):
        super().__init__(name=None, target=target, many=True)

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> LinkList[T]: ...

    @overload
    def __get__(self, obj: object, objtype: Any = None) -> list[T]: ...

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return _AutoLink.__get__(self, obj, objtype)


class AutoLinkedModel(BaseModel, LinkedApiMixin, metaclass=LinkedQueryMeta):
    """Base model supporting both implicit and explicit link declarations."""

    model_config = ConfigDict(ignored_types=(Link, LinkList, _AutoLink))

    _links: dict[str, Any] = PrivateAttr(default_factory=dict)
    _link_cache: dict[str, Any] = PrivateAttr(default_factory=dict)
    __link_fields__: ClassVar[dict[str, _AutoLink]] = {}

    @classmethod
    def oold_query(cls, item: Any) -> Any:
        """Entry point for ``Model[...]``. Wired to a backend in production."""
        return ("query", cls.__name__, item)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        links: dict[str, _AutoLink] = dict(getattr(cls, "__link_fields__", {}))
        # Explicit form: descriptors declared directly in the class body.
        for klass in reversed(cls.__mro__):
            for key, value in vars(klass).items():
                if isinstance(value, _AutoLink):
                    links[key] = value
        # Implicit form: annotated fields carrying a range keyword.
        for name, field in cls.model_fields.items():
            extra = field.json_schema_extra
            if not isinstance(extra, dict):
                continue
            rng = extra.get("x-oold-range", extra.get("range"))
            # x-oold-link marks a link whose target comes from the annotation
            if not rng and not extra.get("x-oold-link"):
                continue
            target, many = _extract_target(field.annotation)
            if isinstance(rng, str) and not isinstance(target, type):
                target = rng
            descr = _AutoLink(name, target, many)
            setattr(cls, name, descr)
            links[name] = descr
        cls.__link_fields__ = links
        # register by the 'type' field default so resolution can dispatch
        type_field = cls.model_fields.get("type")
        if type_field is not None:
            default = type_field.default
            if isinstance(default, str):
                _TYPE_REGISTRY[default] = cls
            elif isinstance(default, list):
                for d in default:
                    if isinstance(d, str):
                        _TYPE_REGISTRY[d] = cls

    def __init__(self, *args: Any, **data: Any) -> None:
        # The shipped model accepts another model as the first positional
        # argument as a cast shorthand: Target(source, extra="value").
        if args and isinstance(args[0], BaseModel):
            source = args[0]
            base = source._raw_dict() if hasattr(source, "_raw_dict") else source.model_dump()
            base.pop("type", None)
            data = {**{k: v for k, v in base.items() if v is not None}, **data}
        elif args:
            raise TypeError(f"{type(self).__name__}() takes no positional arguments other than a source model")
        link_fields = type(self).__link_fields__
        link_data = {k: data.pop(k) for k in list(data) if k in link_fields}
        super().__init__(**data)
        for key, value in link_data.items():
            link_fields[key].set_value(self, value)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "__iris__":
            # a property with a setter on the mixin - pydantic would otherwise
            # reject it as "no field __iris__"
            LinkedApiMixin.__iris__.fset(self, value)
            return
        # Targeted: only link names are routed to the descriptor. Needed because
        # pydantic's own __setattr__ writes model fields straight into __dict__,
        # bypassing a data descriptor's __set__ (which would leave the link
        # storage and its cache stale). Every other write stays native, and
        # BaseModel already defines __setattr__, so this adds no new slot cost.
        descr = type(self).__link_fields__.get(name)
        if descr is not None:
            descr.set_value(self, value)
        else:
            super().__setattr__(name, value)

    def get_iri(self) -> str | None:
        return getattr(self, "id", None)

    def link_iris(self, name: str) -> Any:
        return type(self).__link_fields__[name].iris(self)

    @model_serializer(mode="wrap")
    def _serialize_links(self, handler: Any) -> dict[str, Any]:
        d = handler(self)
        for name, descr in type(self).__link_fields__.items():
            iris = descr.iris(self)
            if iris:
                d[name] = iris
            else:
                d.pop(name, None)
        return d
