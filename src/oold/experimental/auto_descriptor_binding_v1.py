"""Descriptor binding for pydantic **v1** models.

The generated packages emit both a v1 and a v2 variant, and the production entity
models are v1, declaring links with the bare keyword form::

    links: Optional[List[T]] = Field(None, range="T")

so the v1 path is not optional. Detection is simpler here than in v2: pydantic v1
already resolves the target into ``field.type_`` and reports list-ness through
``field.shape``, and the extras land in ``field.field_info.extra``.

The mechanics match the v2 module (:mod:`oold.experimental.auto_descriptor_binding`):
a **non-data** descriptor per link field, resolved values cached in the instance
``__dict__`` so warm reads never re-enter Python, batched resolution, and the
downstream API surface (``get_iri_ref``, ``__iris__``, ``to_json`` ...) preserved.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic.v1 import BaseModel, PrivateAttr
from pydantic.v1.fields import SHAPE_LIST, SHAPE_SET, SHAPE_TUPLE
from pydantic.v1.main import ModelMetaclass

from oold.experimental.auto_descriptor_binding import (
    _TYPE_REGISTRY,
    Condition,
    FieldProxy,
    LinkResultList,
    _batch_resolve,
    _resolve_cls,
)
from oold.experimental.ref_binding import Ref, _construct

_MANY_SHAPES = {SHAPE_LIST, SHAPE_SET, SHAPE_TUPLE}


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

    def __init__(self, name: str, target: Any, many: bool):
        self.name = name
        self.target = target
        self.many = many

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        stored = obj._links.get(self.name)
        if self.many:
            result = LinkResultList(_batch_resolve(stored, self.target)) if stored else LinkResultList()
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


class LinkedQueryMetaV1(ModelMetaclass):
    """Installs link descriptors and provides the class-level query DSL."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        links: dict[str, _AutoLinkV1] = {}
        for base in reversed(cls.__mro__):
            links.update(getattr(base, "__link_fields__", {}) or {})
        for fname, field in getattr(cls, "__fields__", {}).items():
            extra = getattr(field.field_info, "extra", None) or {}
            if not (extra.get("x-oold-range") or extra.get("range") or extra.get("x-oold-link")):
                continue
            # v1 resolves the target for us: type_ is the item type and shape
            # tells us whether the field is to-many
            descr = _AutoLinkV1(fname, field.type_, field.shape in _MANY_SHAPES)
            setattr(cls, fname, descr)
            links[fname] = descr
        cls.__link_fields__ = links
        type_field = getattr(cls, "__fields__", {}).get("type")
        if type_field is not None:
            default = type_field.default
            for d in default if isinstance(default, list) else [default]:
                if isinstance(d, str):
                    _TYPE_REGISTRY[d] = cls
        return cls

    def __getattr__(cls, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        for klass in cls.__mro__:
            fields = klass.__dict__.get("__fields__")
            if fields and name in fields:
                return FieldProxy(name)
        raise AttributeError(name)

    def __getitem__(cls, item: Any) -> Any:
        return cls.oold_query(item)


class AutoLinkedModelV1(BaseModel, metaclass=LinkedQueryMetaV1):
    """pydantic v1 base with the descriptor binding and the downstream API."""

    _links: dict = PrivateAttr(default_factory=dict)
    __link_fields__: dict = {}

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def oold_query(cls, item: Any) -> Any:
        return ("query", cls.__name__, item)

    def __init__(self, *args: Any, **data: Any) -> None:
        if args and isinstance(args[0], BaseModel):
            source = args[0]
            base = source._raw_dict() if hasattr(source, "_raw_dict") else source.dict()
            base.pop("type", None)
            data = {**{k: v for k, v in base.items() if v is not None}, **data}
        link_fields = type(self).__link_fields__
        link_data = {k: data.pop(k) for k in list(data) if k in link_fields}
        super().__init__(**data)
        for key, value in link_data.items():
            link_fields[key].set_value(self, value)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "__iris__":
            for field, iris in (value or {}).items():
                descr = type(self).__link_fields__.get(field)
                if descr is not None:
                    descr.set_value(self, iris)
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
        d = super().dict(**kwargs)
        for name, descr in type(self).__link_fields__.items():
            iris = descr.iris(self)
            if iris:
                d[name] = iris
            elif name in d and not d[name]:
                d[name] = None
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d

    def json(self, **kwargs: Any) -> str:
        return json.dumps(self.dict(**kwargs))

    def to_json(self, exclude_defaults: bool = False) -> dict[str, Any]:
        return self.dict(exclude_none=True, exclude_defaults=exclude_defaults)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Any:
        from oold.static import import_json

        return import_json(BaseModel, cls, cls, data, _TYPE_REGISTRY)

    def to_jsonld(self) -> dict[str, Any]:
        from oold.static import export_jsonld

        return export_jsonld(self, BaseModel)

    @classmethod
    def from_jsonld(cls, jsonld: dict[str, Any]) -> Any:
        from oold.static import import_jsonld

        return import_jsonld(BaseModel, cls, cls, jsonld, _TYPE_REGISTRY)

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
