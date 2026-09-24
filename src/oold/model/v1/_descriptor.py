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

import inspect
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
    _AutoLink,
    _Constructing,
    _default_iris,
)

_MANY_SHAPES = {SHAPE_LIST, SHAPE_SET, SHAPE_TUPLE}

_DICT_KWARGS = frozenset(inspect.signature(BaseModel.dict).parameters) - {"self"}
"""The arguments ``BaseModel.dict`` accepts, which ``json`` has to route to it."""

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


def _neutralise_field(field: Any) -> Any:
    """Make a link field optional and defaultless at the pydantic level.

    Link values are routed around pydantic - the descriptor holds them - so the
    field is always absent from the payload pydantic validates, and a default
    left in place would be evaluated on every construction. Generated models
    spell a default IRI as ``T.parse_obj("<iri>")``, which resolves through the
    backend, so leaving it would also turn every construction into a
    synchronous fetch.

    Returns the declared default IRI(s) so the caller can hand them to the
    descriptor: dropping them outright lost the declared default.
    """
    iris = _default_iris(getattr(field, "field_info", None)) or _default_iris(field)
    field.required = False
    field.allow_none = True
    field.default = None
    field.default_factory = None
    info = getattr(field, "field_info", None)
    if info is not None:
        info.default = None
        info.default_factory = None
    return iris


class _AutoLinkV1(_AutoLink):
    """The shared link descriptor, with v1's way of naming the target.

    Everything else - the construction guard, batched resolution, the instance
    cache, ``set_value``, ``iris`` and the comparison operators - was a
    copy of the v2 descriptor differing only in how the target is reached:
    pydantic v1 resolves it eagerly into ``field.type_``, so there is nothing to
    look up later.
    """

    def _target_cls(self, owner: Any = None) -> Any:
        return self.target


class LinkedBaseModelMetaClass(ModelMetaclass):
    """Installs link descriptors and provides the class-level query DSL."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        _Constructing.enter()
        try:
            cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        finally:
            _Constructing.leave()
        links: dict[str, _AutoLinkV1] = {}
        defaults: dict[str, Any] = {}
        for base in reversed(cls.__mro__):
            links.update(getattr(base, "__link_fields__", {}) or {})
            defaults.update(getattr(base, "__link_defaults__", {}) or {})
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
            # keywords, not positions: the shared __init__ takes
            # (name, target, many, optional, required_iri), and passing
            # required_iri positionally lands it in `optional` - which makes
            # every v1 link mandatory and disables required_iri entirely.
            descr = _AutoLinkV1(
                fname,
                field.type_,
                many=field.shape in _MANY_SHAPES,
                required_iri=required_iri,
            )
            setattr(cls, fname, descr)
            links[fname] = descr
            default_iris = _neutralise_field(field)
            if default_iris is not None:
                defaults[fname] = default_iris
        cls.__link_fields__ = links
        cls.__link_defaults__ = defaults
        _register_class_v1(cls)
        return cls

    def __getattr__(cls, name: str) -> Any:
        if _Constructing.is_active():
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


class LinkedBaseModel(BaseModel, LinkedApiMixin, metaclass=LinkedBaseModelMetaClass):
    """pydantic v1 base with the descriptor binding and the downstream API."""

    _links: dict = PrivateAttr(default_factory=dict)
    __link_fields__: dict = {}
    __link_defaults__: dict = {}

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
        # seed the declared default IRI, which the neutralisation above took off
        # the field: the link then resolves lazily, like any other
        for _name, _iris in type(self).__link_defaults__.items():
            if _name in link_fields and _name not in link_data:
                link_data[_name] = _iris
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
    def _fields(cls) -> dict:
        return cls.__fields__

    def _dump(self, **kwargs: Any) -> dict:
        return self.dict(**kwargs)

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
        # pydantic v1 names the dict() arguments explicitly and collects the
        # rest into **dumps_kwargs. Anything not selecting data - indent,
        # sort_keys, separators - belongs to json.dumps, and dict() raises
        # TypeError on it.
        dumps_kwargs = {key: kwargs.pop(key) for key in list(kwargs) if key not in _DICT_KWARGS}
        return json.dumps(self.dict(**kwargs), default=encoder, **dumps_kwargs)

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
