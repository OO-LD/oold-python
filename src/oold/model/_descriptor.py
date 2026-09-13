"""The descriptor graph-object binding, with no declaration syntax change.

Models are declared exactly as they are today - standard annotations, including
plain ``List[...]`` for to-many links:

    class Person(LinkedBaseModel):
        id: str
        name: Optional[str] = None
        knows: Optional[List["Person"]] = Field(
            None, json_schema_extra={"x-oold-range": "Person"}
        )

so the code ``datamodel-code-generator`` already emits keeps working untouched.
``Link[T]`` / ``LinkList[T]`` are available on top for declarations that should
also be typed in both directions - see ``docs/design/graph-object-binding.md``.

After pydantic finishes building the class, ``__pydantic_init_subclass__`` scans
``model_fields`` for a ``x-oold-range`` (or legacy ``range``) annotation and
installs a descriptor for each such field. Because attribute lookup consults the
type before the instance ``__dict__``, the descriptor handles link reads while
every other field keeps native pydantic access: the "is this a range field?"
test is performed by the interpreter's C-level attribute lookup rather than a
Python ``__getattribute__``, so plain fields cost nothing.

The descriptor is deliberately **non-data** - it defines ``__get__`` but no
runtime ``__set__`` - and caches the resolved value in the instance ``__dict__``,
which then shadows it. Warm link reads are therefore a plain dict lookup that
never re-enters Python (the ``functools.cached_property`` pattern, worth 32x);
writes are intercepted by ``__setattr__`` instead, which drops the cache entry.

Semantics match the shipped binding: reading a link returns the **real** resolved
object (``isinstance`` holds), resolution is lazy, and references serialise back
to IRIs. Resolution is additionally **batched** - a list resolves in one backend
call.

Selected with ``OOLD_DESCRIPTOR_BINDING=1``; ``OOLD_LINKS=0`` turns link
behaviour off entirely and leaves plain pydantic.
"""

from __future__ import annotations

import contextlib
import os
import types
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Generic,
    SupportsIndex,
    TypeVar,
    Union,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SerializationInfo, model_serializer
from pydantic._internal._model_construction import ModelMetaclass
from pydantic_core import PydanticUndefined

from oold.backend import interface
from oold.backend.interface import (
    Condition,
    GetResolverParam,
    QueryParam,
    ResolveParam,
    apply_operator,
    get_resolver,
)
from oold.model._compat import LinkedApiMixin
from oold.model._ref import Ref, _construct

T = TypeVar("T")
_M = TypeVar("_M")


class LinkNotResolved(LookupError):
    """A mandatory link did not yield an object.

    Raised only for links declared ``Link[T]`` rather than ``Link[T | None]``:
    the declaration promises a ``T``, so handing back a ``None`` the type denies
    would be the real error. Declare the ``None`` arm where absence is data.
    """


def links_enabled() -> bool:
    """Whether OO-LD link behaviour is active.

    ``OOLD_LINKS=0`` turns it off: no descriptors are installed, nothing is
    routed out of the payload, and serialisation is pydantic's own. Useful to
    check whether a problem is OO-LD's or the model's, and to run a code base
    as plain pydantic without editing it.
    """
    return os.environ.get("OOLD_LINKS", "1") != "0"


def _neutralise_link_defaults(namespace: dict) -> None:
    """Make link fields optional and defaultless at the pydantic level.

    Link values are routed around pydantic - the descriptor holds them - so the
    field is always absent from the payload pydantic validates. Whatever default
    the declaration carries would therefore be evaluated on every construction,
    and generated models spell that default as ``T.model_validate("<iri>")``,
    which raises: a model cannot be parsed from an IRI string. The descriptor is
    the only source of truth for the value, so the pydantic-level default is
    dead weight and is dropped.

    This runs on the class namespace rather than on ``model_fields``, because by
    the time ``__pydantic_init_subclass__`` sees the fields the core schema -
    defaults included - has already been built.
    """
    import copy as _copy

    def _is_link_field_info(info: Any) -> bool:
        extra = getattr(info, "json_schema_extra", None)
        if not isinstance(extra, dict):
            return False
        return bool(extra.get("x-oold-range") or extra.get("range") or extra.get("x-oold-link"))

    def _neutralised(info: Any) -> Any:
        # Copy first: a FieldInfo can be shared between models (a module-level
        # SHARED = Field(...) assigned to several classes), and mutating it in
        # place stripped that default process-wide, including from plain
        # BaseModels that have nothing to do with links.
        info = _copy.copy(info)
        info.default = None
        info.default_factory = None
        # FieldInfo.from_annotated_attribute rebuilds the field from
        # _attributes_set, so clearing the live attributes alone has no effect
        attributes_set = getattr(info, "_attributes_set", None)
        if isinstance(attributes_set, dict):
            attributes_set = dict(attributes_set)
            attributes_set.pop("default_factory", None)
            attributes_set["default"] = None
            info._attributes_set = attributes_set
        return info

    for field_name, annotation in namespace.get("__annotations__", {}).items():
        info = namespace.get(field_name)
        if _is_link_field_info(info):
            namespace[field_name] = _neutralised(info)
            continue
        # A Field() living in Annotated metadata rather than as the assigned
        # value was never seen here, so its default survived and was evaluated
        # on every construction - the very failure this function exists to stop.
        if get_origin(annotation) is not Annotated:
            continue
        args = get_args(annotation)
        rebuilt = [_neutralised(m) if _is_link_field_info(m) else m for m in args[1:]]
        if rebuilt != list(args[1:]):
            namespace["__annotations__"][field_name] = Annotated[(args[0], *rebuilt)]
            if field_name not in namespace:
                # Annotated-only declarations are required at the pydantic
                # level; the value is routed to the descriptor, so give it the
                # same absent default the assigned form gets.
                namespace[field_name] = None


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
    # bare OoldField() form work with no arguments at all - but only when the
    # caller has not supplied a factory, since pydantic rejects both at once.
    if "default_factory" not in kwargs:
        kwargs.setdefault("default", None)
    return Field(**kwargs, json_schema_extra=extra)


def _has_default(value: Any) -> bool:
    """Whether a field default is a real value rather than a placeholder."""
    return value is not None and value is not ... and value is not PydanticUndefined


class FieldProxy:
    """Class-level field handle enabling ``Person.name == "John"``.

    Carries the field's default as well as its name, because the legacy proxy
    did: downstream writes ``if Model.field:`` and ``Model.type.startswith(...)``
    against class attributes, which resolve to a proxy rather than to the
    default. Without ``__bool__`` every such test is unconditionally true, and
    without ``__getattr__`` every such call raises.
    """

    __slots__ = ("default", "name")

    def __init__(self, name: str, default: Any = None):
        self.name = name
        self.default = default

    def __bool__(self) -> bool:
        return bool(self.default) if _has_default(self.default) else False

    def __getattr__(self, item: str) -> Any:
        default = object.__getattribute__(self, "default")
        if _has_default(default):
            return getattr(default, item)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {item!r}")

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


class LinkedBaseModelMetaClass(ModelMetaclass):
    """Metaclass providing the query DSL without touching attribute reads.

    Uses ``__getattr__`` (a fallback, invoked only when normal lookup *fails*)
    rather than ``__getattribute__`` (invoked on *every* access). Pydantic v2
    removes field names from the class namespace, so ``Person.name`` fails
    naturally and lands here at no cost to any other attribute access.
    """

    _constructing: bool = False
    """Set while a class is being built.

    Pydantic probes ``getattr(base, field_name, None)`` during class
    construction to detect shadowed attributes and inherited defaults. Since
    field names are exactly what ``__getattr__`` answers with a FieldProxy, an
    unguarded proxy is mistaken for an inherited default and ends up as the
    field's value. Same reason the shipped metaclass carries this flag.
    """

    def __new__(mcs, name, bases, namespace, **kwargs):
        if links_enabled():
            _neutralise_link_defaults(namespace)
        LinkedBaseModelMetaClass._constructing = True
        try:
            return super().__new__(mcs, name, bases, namespace, **kwargs)
        finally:
            LinkedBaseModelMetaClass._constructing = False

    def __getattr__(cls, name: str) -> Any:
        # Never call getattr(cls, ...) here: cls.model_fields is a property
        # that itself calls getattr, which would recurse until the stack blows.
        if LinkedBaseModelMetaClass._constructing:
            raise AttributeError(name)
        if name.startswith("_"):
            raise AttributeError(name)
        for klass in cls.__mro__:
            fields = klass.__dict__.get("__pydantic_fields__")
            if fields and name in fields:
                return FieldProxy(name, getattr(fields[name], "default", None))
        raise AttributeError(name)

    @overload
    def __getitem__(cls: type[_M], item: str) -> _M | None: ...

    @overload
    def __getitem__(cls: type[_M], item: Condition | bool) -> LinkResultList[_M] | None: ...

    @overload
    def __getitem__(cls: type[_M], item: list[str]) -> LinkResultList[_M] | None: ...

    def __getitem__(cls, item: Any) -> Any:
        return cls.oold_query(item)


_UNION_ORIGINS = {Union}
if hasattr(types, "UnionType"):  # PEP 604: X | None
    _UNION_ORIGINS.add(types.UnionType)


def _extract_target(annotation: Any) -> tuple[Any, bool, bool]:
    """Return (target_type, is_many, optional) for a link annotation.

    Understands ``Optional[List[X]]`` and the ``Link[X]`` / ``LinkList[X]`` form,
    where the to-many-ness comes from the class rather than a surrounding
    ``list``.

    ``optional`` says whether a missing value is a legitimate answer. Only the
    ``Link[...]`` form can say no: writing ``Link[Person]`` rather than
    ``Link[Person | None]`` declares the link mandatory, and the binding then
    keeps that promise instead of handing back a ``None`` the type denies. Every
    other spelling stays optional, so existing declarations are unaffected.
    """
    many = False
    seen_link_annotation = False
    saw_none_arm = False
    target = annotation
    changed = True
    while changed:
        changed = False
        origin = get_origin(target)
        if isinstance(origin, type) and issubclass(origin, _LinkAnnotation):
            args = get_args(target)
            if args:
                target, changed = args[0], True
                many = many or origin._many
                seen_link_annotation = True
        elif origin in _UNION_ORIGINS:
            # Order-independent: Optional[Link[T]] meets the union first and
            # Link[T | None] meets it second, and both mean the same thing. An
            # earlier version only looked once a Link had been seen, so the
            # outer-Optional spelling came out as its opposite - mandatory.
            if type(None) in get_args(target):
                saw_none_arm = True
            args = [a for a in get_args(target) if a is not type(None)]
            if len(args) == 1:
                target, changed = args[0], True
        elif origin is list:
            args = get_args(target)
            if args:
                target, many, changed = args[0], True, True
    # Only the Link[...] form can declare a link mandatory, and only when no
    # None arm appears anywhere in the annotation.
    optional = not seen_link_annotation or saw_none_arm
    return target, many, optional


def _is_link_annotation(annotation: Any) -> bool:
    """Whether ``Link[...]`` / ``LinkList[...]`` appears anywhere in an annotation.

    Lets the annotation alone declare a link, so ``knows: LinkList["Person"]``
    needs no keyword in ``json_schema_extra``.
    """
    seen: list[Any] = [annotation]
    while seen:
        current = seen.pop()
        origin = get_origin(current)
        if isinstance(origin, type) and issubclass(origin, _LinkAnnotation):
            return True
        seen.extend(get_args(current))
    return False


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


class LinkResultList(list[T]):
    """List returned by a to-many link.

    Adds IRI lookup, filtering and attribute projection, and keeps mutations in
    sync with the owner's link storage: appending or removing an item updates
    the stored references too, so ``__iris__`` and serialisation stay correct
    without a second write.

    Generic in the item type, so ``Entity[cond][0]`` is an ``Entity`` to a type
    checker rather than ``Any``. Whether an element may be ``None`` is declared:
    ``LinkList[Person]`` promises every reference resolves and raises if one does
    not, ``LinkList[Person | None]`` keeps the slot as ``None``. The slot is kept
    either way, so the list stays aligned with the stored references.
    """

    _owner: Any = None
    _field: str | None = None
    _refs: list[Any] | None = None

    def _bind(self, owner: Any, field: str, refs: Any = None) -> LinkResultList:
        self._owner = owner
        self._field = field
        # the references this list was built from, so an entry that could not be
        # resolved can be written back as the reference it still is
        self._refs = list(refs) if refs else []
        return self

    def _sync(self) -> None:
        if self._owner is None or self._field is None:
            return
        # A slot that did not resolve reads as None, but dropping it would
        # delete the reference from storage - the list would shrink and the IRI
        # be lost. `_refs` is kept positionally aligned with this list by every
        # mutator below, so the reference for a None slot is the one at the same
        # index. Matching them up in order instead deleted the wrong element.
        refs = self._refs or []
        values = []
        for index, value in enumerate(self):
            if value is not None:
                values.append(value)
                continue
            ref = refs[index] if index < len(refs) else None
            if ref is not None:
                values.append(ref)
        descr = type(self._owner).__link_fields__[self._field]
        descr.set_value(self._owner, values)
        # keep the cached read pointing at this very list
        self._owner.__dict__[self._field] = self

    # Every mutating operation syncs, and applies the same structural change to
    # _refs so the two stay aligned. Covering only append/remove/extend left
    # `links[0] = x`, `pop()`, `insert()`, `clear()`, `del` and `+=` changing
    # what you see while storage kept the old references.
    def _refs_list(self) -> list:
        if self._refs is None:
            self._refs = []
        return self._refs

    def append(self, item: Any) -> None:
        super().append(item)
        self._refs_list().append(None)
        self._sync()

    def remove(self, item: Any) -> None:
        index = self.index(item)
        super().remove(item)
        refs = self._refs_list()
        if index < len(refs):
            refs.pop(index)
        self._sync()

    def extend(self, iterable: Any) -> None:
        items = list(iterable)
        super().extend(items)
        self._refs_list().extend([None] * len(items))
        self._sync()

    def insert(self, index: SupportsIndex, item: Any) -> None:
        super().insert(index, item)
        self._refs_list().insert(index, None)
        self._sync()

    def pop(self, index: SupportsIndex = -1) -> Any:
        item = super().pop(index)
        refs = self._refs_list()
        with contextlib.suppress(IndexError):
            refs.pop(index)
        self._sync()
        return item

    def clear(self) -> None:
        super().clear()
        self._refs_list().clear()
        self._sync()

    def sort(self, **kwargs: Any) -> None:
        # order becomes unknowable for unresolved slots, so drop their refs
        # rather than pair them with the wrong element
        super().sort(**kwargs)
        self._refs = [None] * len(self)
        self._sync()

    def reverse(self) -> None:
        super().reverse()
        self._refs_list().reverse()
        self._sync()

    def __setitem__(self, index: Any, value: Any) -> None:
        super().__setitem__(index, value)
        refs = self._refs_list()
        if isinstance(index, slice):
            refs[index] = [None] * len(self[index])
        elif index < len(refs):
            refs[index] = None
        self._sync()

    def __delitem__(self, index: Any) -> None:
        super().__delitem__(index)
        refs = self._refs_list()
        with contextlib.suppress(IndexError):
            del refs[index]
        self._sync()

    def __iadd__(self, other: Any) -> LinkResultList:
        items = list(other)
        super().__iadd__(items)
        self._refs_list().extend([None] * len(items))
        self._sync()
        return self

    @overload
    def __getitem__(self, index: Condition | bool) -> LinkResultList[T]: ...

    @overload
    def __getitem__(self, index: SupportsIndex) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> LinkResultList[T]: ...

    @overload
    def __getitem__(self, index: str) -> Any: ...

    def __getitem__(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, index: Any
    ) -> Any:
        if isinstance(index, str):
            if index.startswith("@"):
                # inline query form: links["@name=='Entity 2'"]
                key, _, raw = index[1:].partition("==")
                wanted = raw.strip().strip("'\"")
                return LinkResultList(
                    item for item in self if item is not None and getattr(item, key.strip(), None) == wanted
                )
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
        # Go through resolve(), not resolve_iris(): it applies the backend's
        # format (a JSON-LD store hands back expanded JSON-LD, which cannot be
        # fed to the model directly) and dispatches on the document's type IRI,
        # so a stored subclass resolves to the subclass.
        #
        # A union target (LinkList["Person | Org"]) is not a class, so it cannot
        # be a model_cls. Hand over the root model instead and let the same type
        # dispatch pick the arm - passing the union made ResolveParam validation
        # fail, which used to drop into the fallback below and construct the raw
        # document, i.e. every union link was broken on every JSON-LD backend.
        model_cls = target if isinstance(target, type) else LinkedBaseModel
        try:
            nodes = resolver.resolve(ResolveParam(iris=iris, model_cls=model_cls)).nodes
        except NotImplementedError:
            # A backend that does not implement resolve() at all: fall back to
            # the raw documents. Deliberately narrow - catching everything here
            # turned a malformed document, or any error inside from_jsonld, into
            # a second request whose result was then built against the declared
            # target, losing the original error and silently mis-constructing.
            fetched = resolver.resolve_iris(iris)
            nodes = {
                iri: (_construct(_resolve_cls(d, target), d) if d is not None else None) for iri, d in fetched.items()
            }
        for r in group:
            r._obj = nodes.get(r.iri)
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


def _register_class(cls: type) -> None:
    """Register a class under the type IRIs it introduces.

    Mirrors the shipped metaclass: controllers are collected in a separate
    table so they never shadow the data model they extend, and a data model may
    only claim the IRIs it introduces itself - a subclass that merely narrows a
    field reports its parent's IRI and would otherwise replace it.
    """
    from oold.model import _controller_types, _inherited_cls_iris

    iri = cls.get_cls_iri() if hasattr(cls, "get_cls_iri") else None
    if iri is None:
        return
    is_ctrl = any(b.__module__ == "oold.model" and b.__name__ == "BaseController" for b in cls.__mro__)
    inherited = frozenset() if is_ctrl else _inherited_cls_iris(cls)
    for value in iri if isinstance(iri, list) else [iri]:
        if not isinstance(value, str):
            continue
        if is_ctrl:
            _controller_types.setdefault(value, []).append(cls)
        elif value not in inherited:
            _TYPE_REGISTRY[value] = cls


class _AutoLink:
    """Data descriptor backing a link field.

    Installed automatically for annotated ``x-oold-range`` fields (implicit
    form), or declared directly in a class body via :class:`Link` /
    :class:`LinkList` (explicit form). Both forms share this implementation, so
    runtime behaviour is identical.
    """

    def __init__(
        self,
        name: str | None = None,
        target: Any = None,
        many: bool = False,
        optional: bool = True,
        required_iri: bool = False,
    ):
        self.name = name
        self.target = target
        self.many = many
        # False only for the Link[T] / LinkList[T] form without a None arm
        self.optional = optional
        # x-oold-required-iri: the schema says this link must carry a reference
        self.required_iri = required_iri
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
            if LinkedBaseModelMetaClass._constructing:
                # A subclass may redeclare an inherited link field. Pydantic
                # checks the bases for a same-named attribute and rejects the
                # field if it finds one, so the descriptor has to stay invisible
                # while a class is being built - same reason the metaclass
                # carries the flag.
                raise AttributeError(self.name)
            # Class access returns the descriptor, so Person.knows == "x" can
            # build a Condition without any metaclass involvement.
            return self
        stored = obj._links.get(self.name)
        target = self._target_cls(objtype or type(obj))
        if self.many:
            items = _batch_resolve(stored, target) if stored else []
            if not self.optional and any(item is None for item in items):
                # the declaration promised every element resolves
                missing = [r.iri for r, item in zip(stored, items, strict=False) if item is None]
                raise LinkNotResolved(self._message(obj, missing))
            result = LinkResultList(items)._bind(obj, self.name, stored)
        elif stored is None:
            if not self.optional:
                # Raised on access, not at construction. The annotation says what
                # *reading* the link yields, not that every instance carries one:
                # graph data is routinely partial, and rejecting such objects when
                # they are built would make them unloadable. Declaring the link
                # mandatory states an intent to traverse it, so one try/except
                # around a whole chain replaces a guard at every hop.
                raise LinkNotResolved(
                    f"{type(obj).__name__}.{self.name} is declared mandatory but is "
                    f"not set. Declare it as Link[T | None] if absence is data."
                )
            result = None
        else:
            result = _batch_resolve([stored], target)[0]
            if result is None and not self.optional:
                raise LinkNotResolved(self._message(obj, [stored.iri]))
        # Store the resolved value in the instance __dict__. This descriptor is
        # deliberately NON-data (no __set__), so from now on normal attribute
        # lookup finds the instance dict first and never calls back into Python:
        # warm link reads run at native speed (the functools.cached_property
        # pattern). Writes are still intercepted, by LinkedModel.__setattr__.
        obj.__dict__[self.name] = result
        return result

    def _message(self, obj: Any, iris: list[Any]) -> str:
        listed = ", ".join(str(iri) for iri in iris if iri)
        return (
            f"{type(obj).__name__}.{self.name} is declared mandatory, but "
            f"{listed or 'the reference'} could not be resolved. The backend "
            f"answered without it - declare the link as optional if that is a "
            f"legitimate answer."
        )

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


class _LinkAnnotation:
    """Lets ``Link[T]`` / ``LinkList[T]`` stand in for the target annotation.

    A link has two types, and one annotation cannot state both: what you read is
    a resolved object, what you may write is that object *or* a reference to it
    (an IRI string, or a JSON object still to be constructed). Declaring the
    field as the descriptor type is what carries both - a type checker takes the
    ``__init__`` parameter and the assignment type from ``__set__`` and the
    attribute type from ``__get__`` (PEP 681).

    Pydantic is told to build the schema of the *target* instead, so the emitted
    JSON Schema is byte-identical to the plain annotation - ``$ref``, arrays and
    unions included - and forward references still resolve on ``model_rebuild``.
    """

    _many: ClassVar[bool] = False

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        args = get_args(source_type)
        target = args[0] if args else Any
        return handler(list[target] if cls._many else target)


class Link(_AutoLink, _LinkAnnotation, Generic[T]):
    """A to-one link.

    Two equivalent spellings::

        employer = Link(Organization)        # explicit descriptor
        employer: Link[Organization] = ...   # annotation, and statically typed

    The annotation form is the one that types both directions: it reads as
    ``T | None`` and accepts a ``T``, an IRI or a JSON object on assignment.
    """

    _many: ClassVar[bool] = False

    def __init__(self, target: type[T] | str | None = None):
        super().__init__(name=None, target=target, many=False)

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> Link[T]: ...

    @overload
    def __get__(self, obj: object, objtype: Any = None) -> T: ...

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return _AutoLink.__get__(self, obj, objtype)

    if TYPE_CHECKING:
        # Declared for the checker only. At runtime this stays a **non-data**
        # descriptor, so the instance __dict__ keeps shadowing it after the first
        # read - which is what makes a warm link read cost the same as a plain
        # field. Writes are intercepted by LinkedModel.__setattr__ instead, which
        # applies exactly the conversion declared here.
        def __set__(self, obj: object, value: T | str | Mapping[str, Any] | None) -> None: ...


class LinkList(_AutoLink, _LinkAnnotation, Generic[T]):
    """A to-many link.

    Two equivalent spellings::

        knows = LinkList("Person")        # explicit descriptor
        knows: LinkList["Person"] = ...   # annotation, and statically typed

    The annotation form reads as ``LinkResultList[T | None]`` - never ``None``
    itself, an unset link is an empty list - and accepts objects, IRIs or JSON
    objects on assignment.
    """

    _many: ClassVar[bool] = True

    def __init__(self, target: type[T] | str | None = None):
        super().__init__(name=None, target=target, many=True)

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> LinkList[T]: ...

    @overload
    def __get__(self, obj: object, objtype: Any = None) -> LinkResultList[T]: ...

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        return _AutoLink.__get__(self, obj, objtype)

    if TYPE_CHECKING:
        # see Link.__set__ - checker-only, so the descriptor stays non-data
        def __set__(self, obj: object, value: Iterable[T | str | Mapping[str, Any]] | None) -> None: ...


def _excluded(info: Any, name: str) -> bool:
    """Whether the caller asked for an unset link to be left out."""
    if getattr(info, "exclude_none", False):
        return True
    if getattr(info, "exclude_unset", False) or getattr(info, "exclude_defaults", False):
        return True
    exclude = getattr(info, "exclude", None)
    return bool(exclude) and name in exclude


def _alias_strings(alias: Any) -> list[str]:
    """Every name an alias can be given under.

    ``validation_alias`` is not always a string: ``AliasChoices`` holds several,
    and each may itself be an ``AliasPath``. Accepting only ``str`` left those
    payload keys for pydantic to validate against the *target* model.
    """
    if isinstance(alias, str):
        return [alias]
    choices = getattr(alias, "choices", None)
    if choices is not None:
        out = []
        for choice in choices:
            out.extend(_alias_strings(choice))
        return out
    path = getattr(alias, "path", None)
    if path and isinstance(path[0], str):
        return [path[0]]
    return []


def _link_aliases(cls: type) -> dict[str, str]:
    """alias -> field name, for link fields that declare one.

    Computed once per class in ``__pydantic_init_subclass__`` - it was rebuilt
    on every construction, which cost about a quarter of the time to build an
    object.
    """
    out: dict[str, str] = {}
    for name in getattr(cls, "__link_fields__", {}):
        field = cls.model_fields.get(name)
        for alias in (getattr(field, "validation_alias", None), getattr(field, "alias", None)):
            for text in _alias_strings(alias):
                out[text] = name
    return out


def _emit_inline(stored: Any) -> Any:
    """Serialise references that have no IRI, so they are not silently lost."""

    def one(ref: Any) -> Any:
        obj = getattr(ref, "_obj", None) if ref is not None else None
        if obj is None:
            return None
        return obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else obj

    if isinstance(stored, list):
        return [one(r) for r in stored]
    return one(stored)


class LinkedBaseModel(BaseModel, LinkedApiMixin, metaclass=LinkedBaseModelMetaClass):
    """Base model supporting both implicit and explicit link declarations."""

    model_config = ConfigDict(ignored_types=(Link, LinkList, _AutoLink))

    _links: dict[str, Any] = PrivateAttr(default_factory=dict)
    # references assigned through __iris__ for names that are not link fields;
    # the shipped side-dict kept them, so reading them back has to work
    _extra_iris: dict[str, Any] = PrivateAttr(default_factory=dict)
    __link_fields__: ClassVar[dict[str, _AutoLink]] = {}
    __link_aliases__: ClassVar[dict[str, str]] = {}
    __required_links__: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def oold_query(cls, item: Any) -> Any:
        """Resolve ``Model[...]`` against every registered resolver.

        A single IRI yields one instance, a list or a condition yields a list.
        Resolvers that cannot answer a structured query are skipped.
        """
        node_list: list = []
        for resolver in interface._resolvers.values():
            try:
                if isinstance(item, (str, list)):
                    nodes = resolver.resolve(
                        ResolveParam(
                            iris=[item] if isinstance(item, str) else item,
                            model_cls=cls,
                        )
                    ).nodes.values()
                else:
                    nodes = resolver.query(QueryParam(query=item, model_cls=cls)).nodes.values()
                node_list.extend(nodes)
            except NotImplementedError:
                continue
        # A query answers with what it found. An IRI the backend cannot place is
        # not a match, and keeping a None for it would contradict the element
        # type - unlike a to-many link, there is no declaration here promising
        # the result stays aligned with anything.
        node_list = [node for node in node_list if node is not None]
        if isinstance(item, str):
            return node_list[0] if node_list else None
        return LinkResultList(node_list) if node_list else None

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not links_enabled():
            # Plain-pydantic mode: install nothing. Link fields keep the
            # semantics their annotation already states - a nested model, not
            # an IRI reference - so the class behaves exactly like a plain
            # BaseModel without touching the declaration.
            cls.__link_fields__ = {}
            return
        links: dict[str, _AutoLink] = dict(getattr(cls, "__link_fields__", {}))
        # Explicit form: descriptors declared directly in the class body.
        for klass in reversed(cls.__mro__):
            for key, value in vars(klass).items():
                if isinstance(value, _AutoLink):
                    links[key] = value
        # Implicit form: annotated fields carrying a range keyword.
        for name, field in cls.model_fields.items():
            extra = field.json_schema_extra
            extra = extra if isinstance(extra, dict) else {}
            rng = extra.get("x-oold-range", extra.get("range"))
            # x-oold-link marks a link whose target comes from the annotation;
            # a Link[...] / LinkList[...] annotation says the same on its own
            if not rng and not extra.get("x-oold-link") and not _is_link_annotation(field.annotation):
                continue
            target, many, optional = _extract_target(field.annotation)
            if isinstance(rng, str) and not isinstance(target, type):
                target = rng
            descr = _AutoLink(name, target, many, optional, bool(extra.get("x-oold-required-iri")))
            setattr(cls, name, descr)
            links[name] = descr
        cls.__link_fields__ = links
        # per-class constants, so construction does not recompute them
        cls.__link_aliases__ = _link_aliases(cls)
        cls.__required_links__ = tuple(n for n, d in links.items() if d.required_iri)
        _register_class(cls)

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
        # Route link values out of the payload before pydantic validates - by
        # field name and by alias, since a payload built with by_alias=True uses
        # the alias and would otherwise be validated against the target model.
        aliases = type(self).__link_aliases__
        link_data = {}
        for key in list(data):
            name = key if key in link_fields else aliases.get(key)
            if name is not None:
                link_data[name] = data.pop(key)
        super().__init__(**data)
        # Pydantic writes each field's default into __dict__, and an entry there
        # shadows a non-data descriptor - so an unset link would keep returning
        # that default (None) and never reach __get__. Dropping the entries hands
        # unset links back to the descriptor, which answers [] for to-many and
        # None for to-one. That is what makes a non-Optional list annotation
        # truthful rather than a lie about a value that is really None.
        for _name in link_fields:
            self.__dict__.pop(_name, None)
        for key, value in link_data.items():
            link_fields[key].set_value(self, value)
        missing = [name for name in type(self).__required_links__ if not self._links.get(name)]
        if missing:
            # x-oold-required-iri, enforced as the legacy binding did. It raised
            # on the mere presence of the keyword; this raises on a true value,
            # so required_iri=False no longer means "required".
            raise ValueError(f"{', '.join(sorted(missing))} is required but not set")

    def __eq__(self, other: Any) -> bool:
        """Compare by data, not by what happens to be cached.

        Resolving a link stores the resolved object in ``__dict__`` (that is
        what makes warm reads native-speed), and pydantic's ``__eq__`` compares
        ``__dict__`` - so reading a link would otherwise change the result of a
        comparison. Links are compared by their stored references instead, and
        the remaining fields the normal way.
        """
        if other.__class__ is not self.__class__:
            return NotImplemented
        # Compare the same state pydantic does - extras and private attributes
        # included. Looking at __dict__ alone made two models with different
        # extra="allow" fields compare equal.
        if self.__pydantic_extra__ != other.__pydantic_extra__:
            return False
        if self.__pydantic_private__ != other.__pydantic_private__:
            return False
        links = type(self).__link_fields__
        if links:
            mine = {k: v for k, v in self.__dict__.items() if k not in links}
            theirs = {k: v for k, v in other.__dict__.items() if k not in links}
            if mine != theirs:
                return False
            return all(links[name].iris(self) == links[name].iris(other) for name in links)
        return self.__dict__ == other.__dict__

    __hash__ = None  # type: ignore[assignment]
    """Unhashable, as pydantic models are.

    An earlier ``__hash__ = id(self)`` made models hashable, so ``set(models)``
    deduplicated by identity instead of raising - silently different from both
    the legacy binding and plain pydantic.
    """

    def __setattr__(self, name: str, value: Any, internal: bool = False) -> None:
        # internal=True means "write the value as given": BaseController passes
        # it through to bypass link handling for controller-only state.
        if name == "__iris__":
            # a property with a setter on the mixin - pydantic would otherwise
            # reject it as "no field __iris__"
            LinkedApiMixin.__iris__.fset(self, value)
            return
        if internal:
            super().__setattr__(name, value)
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

    @model_serializer(mode="wrap")
    def _serialize_links(self, handler: Any, info: SerializationInfo) -> dict[str, Any]:
        d = handler(self)
        fields = type(self).model_fields
        by_alias = bool(getattr(info, "by_alias", False))
        for name, descr in type(self).__link_fields__.items():
            # honour by_alias: every other key does, so writing the link under
            # its field name produced a payload mixing both spellings. The key
            # is never in `d` to compare against - link values are routed out of
            # __dict__ - so the decision comes from the serialisation context.
            name_out = name
            if by_alias:
                field = fields.get(name)
                alias = getattr(field, "serialization_alias", None) or getattr(field, "alias", None)
                if isinstance(alias, str):
                    name_out = alias
            iris = descr.iris(self)
            if iris:
                d.pop(name, None)
                d[name_out] = iris
                continue
            stored = self._links.get(name)
            if stored is None and name not in self._links:
                # Never set: emit the key holding None, as the legacy binding
                # does - but only when the caller has not asked for exactly this
                # to be left out. Writing it unconditionally runs *after*
                # handler() has applied the exclusions, which would leak an
                # explicit null past exclude_none, exclude_unset,
                # exclude_defaults and exclude={...} into every stored document.
                d.pop(name, None)
                if not _excluded(info, name):
                    d[name_out] = None
                continue
            # Set, but nothing to reference: either an explicit empty list - a
            # different statement from "unset" and one that must round-trip - or
            # an inline object with no IRI, which has to serialise nested rather
            # than vanish, since cast() is built on this.
            d.pop(name, None)
            d[name_out] = _emit_inline(stored)
        return d


# Downstream subclasses this metaclass by name, so the name is public API and
# must stay bound to whatever metaclass LinkedBaseModel actually uses.
LinkedQueryMeta = LinkedBaseModelMetaClass
