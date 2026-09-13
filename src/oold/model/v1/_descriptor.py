"""Descriptor binding for pydantic **v1** models.

The generated packages emit both a v1 and a v2 variant, and the production entity
models are v1, declaring links with the bare keyword form::

    links: Optional[List[T]] = Field(None, range="T")

so the v1 path is not optional. Detection is simpler here than in v2: pydantic v1
already resolves the target into ``field.type_`` and reports list-ness through
``field.shape``, and the extras land in ``field.field_info.extra``.

The mechanics match the v2 module (:mod:`oold.model._descriptor`):
a **non-data** descriptor per link field, resolved values cached in the instance
``__dict__`` so warm reads never re-enter Python, batched resolution, and the
downstream API surface (``get_iri_ref``, ``__iris__``, ``to_json`` ...) preserved.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar, overload

from pydantic.v1 import BaseModel, PrivateAttr
from pydantic.v1.fields import SHAPE_LIST, SHAPE_SET, SHAPE_TUPLE
from pydantic.v1.main import ModelMetaclass

from oold.model._compat import LinkedApiMixin
from oold.model._descriptor import (
    Condition,
    FieldProxy,
    LinkResultList,
    _batch_resolve,
    _resolve_cls,
)
from oold.model._ref import Ref, _construct
from oold.static import GenericLinkedBaseModel

_MANY_SHAPES = {SHAPE_LIST, SHAPE_SET, SHAPE_TUPLE}

_M = TypeVar("_M")

_TYPE_REGISTRY: dict[str, type] = {}
"""Type IRI -> model class.

Kept separate from the v2 registry: the two live in different pydantic worlds,
and a v2 class handed to v1 deserialisation would fail to validate.
"""

_CONTROLLER_REGISTRY: dict[str, list] = {}


def use_type_registry(registry: dict, controllers: dict | None = None) -> None:
    """Write registrations into ``registry`` instead of the module-local one.

    Downstream code imports ``oold.model.v1._types`` and writes to it directly,
    so the binding has to share that very mapping rather than keep its own -
    otherwise resolution silently falls back to the declared target.
    """
    global _TYPE_REGISTRY, _CONTROLLER_REGISTRY
    registry.update(_TYPE_REGISTRY)
    _TYPE_REGISTRY = registry
    if controllers is not None:
        controllers.update(_CONTROLLER_REGISTRY)
        _CONTROLLER_REGISTRY = controllers


def _register_class_v1(cls: type) -> None:
    """Register a class under the type IRIs it introduces.

    Mirrors the shipped v1 metaclass: controllers are collected separately so
    they never shadow the data model they extend, and a class may only claim the
    IRIs it introduces itself - a subclass that merely narrows a field reports
    its parent's IRI and would otherwise replace it.
    """
    from oold.model import _inherited_cls_iris

    iri = cls.get_cls_iri() if hasattr(cls, "get_cls_iri") else None
    if iri is None:
        return
    is_ctrl = any(b.__name__ == "BaseController" for b in cls.__mro__)
    inherited = frozenset() if is_ctrl else _inherited_cls_iris(cls)
    for value in iri if isinstance(iri, list) else [iri]:
        if not isinstance(value, str):
            continue
        if is_ctrl:
            _CONTROLLER_REGISTRY.setdefault(value, []).append(cls)
        elif value not in inherited:
            _TYPE_REGISTRY[value] = cls


def _neutralise_field(field: Any) -> None:
    """Make a link field optional and defaultless at the pydantic level.

    Link values are routed around pydantic - the descriptor holds them - so the
    field is always absent from the payload pydantic validates. Whatever default
    the declaration carries would therefore be evaluated on every construction,
    and generated models spell that default as ``T.parse_obj("<iri>")``, which
    raises: a model cannot be parsed from an IRI string. The descriptor is the
    only source of truth for the value, so the pydantic-level default is dead
    weight and is dropped.
    """
    field.required = False
    field.allow_none = True
    field.default = None
    field.default_factory = None
    info = getattr(field, "field_info", None)
    if info is not None:
        info.default = None
        info.default_factory = None


def _to_ref_v1(value: Any, target: Any) -> Ref | None:
    if value is None:
        return None
    if isinstance(value, Ref):
        if value._target is None:
            value._target = target
        return value
    if isinstance(value, str):
        return Ref(iri=value, target=target)
    if isinstance(value, dict):
        cls = _resolve_cls(value, target)
        if cls is None:
            raise ValueError(f"Cannot construct link from {value!r}: unknown target")
        return Ref(obj=_construct(cls, value), target=target)
    return Ref(obj=value, target=target)


class _AutoLinkV1:
    """Non-data descriptor backing a v1 link field."""

    def __init__(self, name: str, target: Any, many: bool, required_iri: bool = False):
        self.name = name
        self.target = target
        self.many = many
        # x-oold-required-iri: the schema says this link must carry a reference
        self.required_iri = required_iri

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            if LinkedBaseModelMetaClass._constructing:
                # A subclass may redeclare an inherited link field. pydantic v1
                # rejects a field whose name resolves to a truthy attribute on a
                # base (validate_field_name), so the descriptor has to stay
                # invisible while a class is being built - same reason the
                # metaclass carries the flag.
                raise AttributeError(self.name)
            return self
        stored = obj._links.get(self.name)
        if self.many:
            result = (LinkResultList(_batch_resolve(stored, self.target)) if stored else LinkResultList())._bind(
                obj, self.name, stored
            )
        elif stored is None:
            result = None
        else:
            result = _batch_resolve([stored], self.target)[0]
        # non-data descriptor: the instance dict shadows it from now on, so
        # subsequent reads are a plain C-level lookup
        obj.__dict__[self.name] = result
        return result

    def set_value(self, obj: Any, value: Any) -> None:
        obj.__dict__.pop(self.name, None)  # invalidate the cached read
        if self.many:
            obj._links[self.name] = [] if value is None else [_to_ref_v1(v, self.target) for v in value]
        else:
            obj._links[self.name] = _to_ref_v1(value, self.target)

    def iris(self, obj: Any) -> Any:
        stored = obj._links.get(self.name)
        if self.many:
            return [r.iri for r in (stored or []) if r is not None and r.iri]
        return stored.iri if stored is not None else None

    def __eq__(self, other: Any) -> Any:  # type: ignore[override]
        return Condition(field=self.name, operator="eq", value=other)

    def __hash__(self) -> int:
        return id(self)


class LinkedBaseModelMetaClass(ModelMetaclass):
    """Installs link descriptors and provides the class-level query DSL."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        LinkedBaseModelMetaClass._constructing = True
        try:
            cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        finally:
            LinkedBaseModelMetaClass._constructing = False
        links: dict[str, _AutoLinkV1] = {}
        for base in reversed(cls.__mro__):
            links.update(getattr(base, "__link_fields__", {}) or {})
        for fname, field in getattr(cls, "__fields__", {}).items():
            extra = getattr(field.field_info, "extra", None) or {}
            if not (extra.get("x-oold-range") or extra.get("range") or extra.get("x-oold-link")):
                continue
            # v1 resolves the target for us: type_ is the item type and shape
            # tells us whether the field is to-many
            # v1 cannot pass a hyphenated keyword to Field(), so downstream
            # spells it with underscores - the legacy v1 binding reads only that
            # form. Accept both.
            required_iri = bool(extra.get("x_oold_required_iri") or extra.get("x-oold-required-iri"))
            descr = _AutoLinkV1(fname, field.type_, field.shape in _MANY_SHAPES, required_iri)
            setattr(cls, fname, descr)
            links[fname] = descr
            _neutralise_field(field)
        cls.__link_fields__ = links
        _register_class_v1(cls)
        return cls

    _constructing: bool = False
    """Set while a class is being built.

    pydantic v1 calls ``hasattr(base, field_name)`` to reject fields that shadow
    a BaseModel attribute. Field names are exactly what ``__getattr__`` answers
    with a FieldProxy, so without this guard every model declaring ``type``
    fails to build. Same reason the v2 metaclass carries the flag.
    """

    def __getattr__(cls, name: str) -> Any:
        if LinkedBaseModelMetaClass._constructing:
            raise AttributeError(name)
        if name.startswith("_"):
            raise AttributeError(name)
        for klass in cls.__mro__:
            fields = klass.__dict__.get("__fields__")
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


class LinkedBaseModel(BaseModel, GenericLinkedBaseModel, metaclass=LinkedBaseModelMetaClass):
    """pydantic v1 base with the descriptor binding and the downstream API."""

    _links: dict = PrivateAttr(default_factory=dict)
    __link_fields__: dict = {}

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def oold_query(cls, item: Any) -> Any:
        """Resolve ``Model[...]`` against every registered resolver."""
        from oold.backend import interface
        from oold.backend.interface import QueryParam, ResolveParam

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
        if isinstance(item, str):
            return node_list[0] if node_list else None
        return LinkResultList(node_list) if node_list else None

    def __init__(self, *args: Any, **data: Any) -> None:
        if args and isinstance(args[0], BaseModel):
            source = args[0]
            base = source._raw_dict() if hasattr(source, "_raw_dict") else source.dict()
            base.pop("type", None)
            data = {**{k: v for k, v in base.items() if v is not None}, **data}
        link_fields = type(self).__link_fields__
        link_data = {k: data.pop(k) for k in list(data) if k in link_fields}
        super().__init__(**data)
        # Pydantic writes each field's default into __dict__, and an entry there
        # shadows a non-data descriptor - so an unset link would keep returning
        # that default (None) and never reach __get__. Dropping the entries hands
        # unset links back to the descriptor, which answers [] for to-many and
        # None for to-one.
        for _name in link_fields:
            self.__dict__.pop(_name, None)
        for key, value in link_data.items():
            link_fields[key].set_value(self, value)
        missing = [name for name, d in link_fields.items() if d.required_iri and not self._links.get(name)]
        if missing:
            # see the v2 note: enforced on a true value, not on key presence
            raise ValueError(f"{', '.join(sorted(missing))} is required but not set")

    def __setattr__(self, name: str, value: Any, internal: bool = False) -> None:
        # internal=True means "write the value as given": BaseController passes
        # it through to bypass link handling for controller-only state.
        if name == "__iris__":
            # delegate to the shared property, so a v1 model gets the same
            # replace semantics as a v2 one
            LinkedApiMixin.__iris__.fset(self, value)
            return
        if internal:
            super().__setattr__(name, value)
            return
        descr = type(self).__link_fields__.get(name)
        if descr is not None:
            descr.set_value(self, value)
        else:
            super().__setattr__(name, value)

    # -- downstream API -----------------------------------------------------

    @property
    def __iris__(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, descr in type(self).__link_fields__.items():
            iris = descr.iris(self)
            if iris:
                out[name] = iris
        return out

    @classmethod
    def get_type_field(cls) -> str:
        return "type"

    @classmethod
    def get_cls_iri(cls) -> Any:
        """The class IRI(s), from ``Config.schema_extra`` and the type default."""
        schema = getattr(getattr(cls, "__config__", None), "schema_extra", None) or {}
        if callable(schema):
            schema = {}
        out: list[str] = []
        for key in ("$id", "x-oold-iri", "iri"):
            if key in schema:
                out.append(schema[key])
                break
        type_field = cls.__fields__.get(cls.get_type_field())
        if type_field is not None:
            default = type_field.default
            for value in default if isinstance(default, list) else [default]:
                if isinstance(value, str) and value not in out:
                    out.append(value)
        if not out:
            return None
        return out[0] if len(out) == 1 else out

    def get_iri_ref(self, field_name: str) -> Any:
        iris = self.__iris__.get(field_name)
        if iris is None:
            return None
        if isinstance(iris, list):
            return iris if iris else None
        return iris

    def get_raw(self, field_name: str) -> Any:
        descr = type(self).__link_fields__.get(field_name)
        if descr is None:
            return self.__dict__.get(field_name)
        stored = self._links.get(field_name)
        if isinstance(stored, list):
            return [r._obj for r in stored if r is not None] or None
        return stored._obj if stored is not None else None

    def get_iri(self) -> str | None:
        return getattr(self, "id", None)

    def link_iris(self, name: str) -> Any:
        return type(self).__link_fields__[name].iris(self)

    def _raw_dict(self) -> dict[str, Any]:
        links = type(self).__link_fields__
        d: dict[str, Any] = {}
        for name in type(self).__fields__:
            if name in links:
                d[name] = self.get_iri_ref(name)
                continue
            value = self.__dict__.get(name)
            if isinstance(value, list):
                d[name] = [
                    v._raw_dict() if hasattr(v, "_raw_dict") else (v.dict() if hasattr(v, "dict") else v) for v in value
                ]
            elif hasattr(value, "_raw_dict"):
                d[name] = value._raw_dict()
            elif hasattr(value, "dict"):
                d[name] = value.dict()
            else:
                d[name] = value
        return d

    def dict(self, **kwargs: Any) -> dict[str, Any]:
        """v1 serialisation; link fields collapse to their IRIs."""
        exclude_none = kwargs.pop("exclude_none", False)
        links = type(self).__link_fields__
        # Reading a link caches the resolved value in __dict__, which pydantic v1
        # serialises - so whether a link had been read changed the output. Drop
        # the cache entries for the duration, then restore them.
        cached = {name: self.__dict__.pop(name) for name in links if name in self.__dict__}
        try:
            d = super().dict(**kwargs)
        finally:
            self.__dict__.update(cached)
        for name, descr in links.items():
            iris = descr.iris(self)
            if iris:
                d[name] = iris
            else:
                d[name] = None
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d

    def json(self, **kwargs: Any) -> str:
        # dict() leaves UUIDs, datetimes and enums as Python objects, so the
        # model's own encoder has to do the conversion - plain json.dumps
        # rejects them.
        encoder = kwargs.pop("encoder", None) or self.__json_encoder__
        kwargs.pop("models_as_dict", None)
        return json.dumps(self.dict(**kwargs), default=encoder)

    def to_json(self, exclude_defaults: bool = False) -> dict[str, Any]:
        return json.loads(self.json(exclude_none=True, exclude_defaults=exclude_defaults))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Any:
        from oold.static import import_json

        return import_json(BaseModel, LinkedBaseModel, cls, data, _TYPE_REGISTRY)

    def to_jsonld(self) -> dict[str, Any]:
        from oold.static import export_jsonld

        return export_jsonld(self, BaseModel)

    @classmethod
    def from_jsonld(cls, jsonld: dict[str, Any]) -> Any:
        from oold.static import import_jsonld

        return import_jsonld(BaseModel, LinkedBaseModel, cls, jsonld, _TYPE_REGISTRY)

    def store_jsonld(self) -> None:
        from oold.backend.interface import GetBackendParam, StoreParam, get_backend

        backend = get_backend(GetBackendParam(iri=self.get_iri())).backend
        backend.store(StoreParam(nodes={self.get_iri(): self}))

    def cast(
        self,
        cls: type,
        none_to_default: bool = False,
        remove_extra: bool = False,
        silent: bool = True,
        **kwargs: Any,
    ) -> Any:
        data = {**self._raw_dict(), **kwargs}
        if none_to_default:
            data = {
                k: v
                for k, v in data.items()
                if v is not None and not (isinstance(v, list) and not [x for x in v if x is not None])
            }
        if remove_extra:
            target = set(getattr(cls, "__fields__", {}))
            if target:
                data = {k: v for k, v in data.items() if k in target}
        data.pop("type", None)
        return cls(**data)

    def cast_none_to_default(self, cls: type, **kwargs: Any) -> Any:
        return self.cast(cls, none_to_default=True, **kwargs)


LinkedQueryMetaV1 = LinkedBaseModelMetaClass
