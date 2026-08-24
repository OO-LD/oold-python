"""Public-API parity layer for the descriptor binding.

Downstream code (the generated ``opensemantic.*`` packages and the applications
built on them) inherits its API from ``oold.model.LinkedBaseModel`` via
``OswBaseModel``. Replacing the binding therefore has to keep that surface
working. A scan of those code bases found these members in active use:

===========================  =====  =================================
member                       sites  note
===========================  =====  =================================
``get_iri_ref``                 24  hand-written application code
``__iris__``                    15  read **and written** by callers
``get_cls_iri``                 42  inherited, unchanged
``to_json`` / ``from_json``      9  each
``to_jsonld`` / ``from_jsonld``  4  / 1
``cast`` / ``cast_none_to_default``  3 / 2
``get_raw``                      2
===========================  =====  =================================

``LinkedBaseModelList`` and ``store_jsonld`` had no downstream hits.

The mixin below re-implements that surface on top of the descriptor storage
(``_links``), reusing :mod:`oold.static` for the RDF work so behaviour matches
the shipped model rather than being re-derived.

``__iris__`` is a read/write property: the shipped model exposes a plain dict
and callers assign to it directly, e.g. in ``opensemantic.base``::

    self.__iris__ = {"characteristic": characteristic_class.get_cls_iri()}

so a read-only shim would silently drop such assignments.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from oold.static import (
    GenericLinkedBaseModel,
    export_jsonld,
    import_json,
    import_jsonld,
)


class LinkedApiMixin(GenericLinkedBaseModel):
    """Re-implements the shipped ``LinkedBaseModel`` API over ``_links``."""

    # -- reference inspection, no resolution --------------------------------

    @property
    def __iris__(self) -> dict[str, Any]:
        """The stored IRI reference(s) per link field.

        Mirrors the shipped side-dict. Writable: assigning a mapping replaces
        the stored references, which is what external code relies on.
        """
        out: dict[str, Any] = {}
        for name, descr in type(self).__link_fields__.items():
            iris = descr.iris(self)
            if iris:
                out[name] = iris
        return out

    @__iris__.setter
    def __iris__(self, value: dict[str, Any]) -> None:
        link_fields = type(self).__link_fields__
        for name, iris in (value or {}).items():
            descr = link_fields.get(name)
            if descr is None:
                continue
            descr.set_value(self, iris)

    @classmethod
    def get_cls_iri(cls) -> Any:
        """The class IRI(s), from the schema annotation and the type default.

        ``GenericLinkedBaseModel`` only declares this abstract, so without an
        implementation it silently returns ``None`` - which would break the
        downstream callers and the type registry alike.
        """
        schema = getattr(cls, "model_config", {}).get("json_schema_extra") or {}
        if callable(schema):
            schema = {}
        out: list[str] = []
        for key in ("$id", "x-oold-iri", "iri"):
            if key in schema:
                out.append(schema[key])
                break
        type_field = cls.model_fields.get(cls.get_type_field())
        if type_field is not None:
            default = type_field.default
            for value in default if isinstance(default, list) else [default]:
                if isinstance(value, str) and value not in out:
                    out.append(value)
        if not out:
            return None
        return out[0] if len(out) == 1 else out

    def get_iri_ref(self, field_name: str) -> Any:
        """IRI reference(s) for a field, or ``None``, without resolving."""
        iris = self.__iris__.get(field_name)
        if iris is None:
            return None
        if isinstance(iris, list):
            return iris if iris else None
        return iris

    def get_raw(self, field_name: str) -> Any:
        """The stored value without triggering resolution."""
        descr = type(self).__link_fields__.get(field_name)
        if descr is None:
            return self.__dict__.get(field_name)
        stored = self._links.get(field_name)
        if isinstance(stored, list):
            return [r._obj for r in stored if r is not None] or None
        return stored._obj if stored is not None else None

    # -- serialisation ------------------------------------------------------

    def _raw_dict(self) -> dict[str, Any]:
        """Serialise without resolving; links become IRI strings.

        Mirrors the shipped ``_raw_dict``: **every** declared field appears, with
        ``None`` where unset. ``cast()`` is built on this, so omitting empty
        fields would silently drop them from the target.
        """
        links = type(self).__link_fields__
        d: dict[str, Any] = {}
        for name in type(self).model_fields:
            if name in links:
                d[name] = self.get_iri_ref(name)
                continue
            value = self.__dict__.get(name)
            if isinstance(value, list):
                d[name] = [
                    v._raw_dict() if hasattr(v, "_raw_dict") else (v.model_dump() if hasattr(v, "model_dump") else v)
                    for v in value
                ]
            elif hasattr(value, "_raw_dict"):
                d[name] = value._raw_dict()
            elif hasattr(value, "model_dump"):
                d[name] = value.model_dump()
            else:
                d[name] = value
        return d

    def to_json(self, exclude_defaults: bool = False) -> dict[str, Any]:
        result = json.loads(self.model_dump_json(exclude_none=True, exclude_defaults=exclude_defaults))
        for name in type(self).__link_fields__:
            iri = self.get_iri_ref(name)
            if iri is not None and not result.get(name):
                result[name] = iri
        return result

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Any:
        from oold.experimental.auto_descriptor_binding import _TYPE_REGISTRY

        return import_json(BaseModel, cls, cls, data, _TYPE_REGISTRY)

    def to_jsonld(self) -> dict[str, Any]:
        return export_jsonld(self, BaseModel)

    @classmethod
    def from_jsonld(cls, jsonld: dict[str, Any]) -> Any:
        from oold.experimental.auto_descriptor_binding import _TYPE_REGISTRY

        return import_jsonld(BaseModel, cls, cls, jsonld, _TYPE_REGISTRY)

    def store_jsonld(self) -> None:
        from oold.backend.interface import GetBackendParam, StoreParam, get_backend

        backend = get_backend(GetBackendParam(iri=self.get_iri())).backend
        backend.store(StoreParam(nodes={self.get_iri(): self}))

    # -- conversion ---------------------------------------------------------

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
            target = set(getattr(cls, "model_fields", {}))
            if target:
                data = {k: v for k, v in data.items() if k in target}
        data.pop("type", None)
        return cls(**data)

    def cast_none_to_default(self, cls: type, **kwargs: Any) -> Any:
        return self.cast(cls, none_to_default=True, **kwargs)
