"""Prototype: transparent descriptor-based graph-object binding (recommended).

This is the recommended binding in ``docs/design/graph-object-binding.md``. It
keeps the shipped library's ergonomics - plain attribute access returns the
**real** resolved object, so ``isinstance(person.knows[0], Person)`` is true and
the value can be passed anywhere a ``Person`` is expected - while removing the
three things that make the shipped implementation heavy:

- no metaclass and no per-attribute ``__getattribute__`` override (only link
  fields are descriptors, so plain fields keep native pydantic access);
- no process-wide ``pydantic.fields.FieldInfo`` monkeypatch;
- no ``__iris__`` side-dict duplicating field state.

Compared with the explicit ``Ref[T]`` prototype (``ref_binding.py``), this form
is *transparent*: resolution is implicit (reading a link may hit the backend,
exactly as today). The two are complementary - a link field also exposes an
explicit handle (``Person.knows.iris(p)`` / ``refs(p)`` / ``aresolve(p)``) for
callers that want batched or asynchronous control. Use the descriptor form for
drop-in parity; reach for the explicit handle where visible I/O matters.

Design:

- ``Link[T]`` / ``LinkList[T]`` are generic **data descriptors**. Declared
  *without* a type annotation (``knows = LinkList[Person](Person)``), so pydantic
  never treats them as fields; static typing comes from the descriptor's typed
  ``__get__`` (the SQLAlchemy-relationship pattern), so ``person.knows`` is
  ``list[Person]``.
- ``LinkedModel`` stores references in a private ``_links`` dict (each a
  :class:`~oold.experimental.ref_binding.Ref`), routes link kwargs in
  ``__init__``, intercepts writes only for link names in ``__setattr__``, and
  materialises link IRIs on serialisation.
- Resolution is **batched**: reading a ``LinkList`` resolves all its IRIs in one
  backend call and caches them.

Importing this module does not patch ``FieldInfo`` (it only touches
``oold.backend`` and ``ref_binding``).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from typing import (
    Any,
    ClassVar,
    Dict,
    Generic,
    List,
    Optional,
    TypeVar,
    Union,
    overload,
)

from pydantic import BaseModel, ConfigDict, PrivateAttr, model_serializer

from oold.backend.interface import GetResolverParam, get_resolver
from oold.experimental.ref_binding import Ref, _construct

T = TypeVar("T")


def _resolve_target(target: Union[type, str, None], owner: Optional[type]) -> Any:
    """Resolve a target given as a class or a (possibly forward-ref) name."""
    if isinstance(target, str) and owner is not None:
        module = sys.modules.get(owner.__module__)
        if module is not None and hasattr(module, target):
            return getattr(module, target)
    return target


def _batch_resolve(refs: List[Optional[Ref]], target: Any) -> List[Any]:
    """Resolve every unresolved Ref in one backend call per resolver prefix.

    Caches the resolved object on each Ref and returns the real objects. This is
    the batching the explicit per-Ref form loses: one ``resolve_iris`` call for a
    whole list rather than one per item.
    """
    pending = [r for r in refs if r is not None and r._obj is None and r.iri]
    groups: Dict[str, List[Ref]] = defaultdict(list)
    for r in pending:
        groups[r.iri.split(":")[0]].append(r)
    for group in groups.values():
        iris = [r.iri for r in group]
        resolver = get_resolver(GetResolverParam(iri=iris[0])).resolver
        fetched = resolver.resolve_iris(iris)
        for r in group:
            d = fetched.get(r.iri)
            r._obj = _construct(target, d) if d is not None else None
    return [None if r is None else r._obj for r in refs]


def _to_ref(value: Any, target: Any) -> Ref:
    if isinstance(value, Ref):
        if value._target is None:
            value._target = target
        return value
    if isinstance(value, str):
        return Ref(iri=value, target=target)
    return Ref(obj=value, target=target)


class LinkList(Generic[T]):
    """Data descriptor for a to-many ``x-oold-range`` link. Reads as ``list[T]``."""

    many = True

    def __init__(self, target: "type[T] | str"):
        self._target = target
        self.name: Optional[str] = None
        self.owner: Optional[type] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.owner = owner

    def _target_cls(self) -> Any:
        return _resolve_target(self._target, self.owner)

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> "LinkList[T]":
        ...

    @overload
    def __get__(self, obj: object, objtype: Any = None) -> List[T]:
        ...

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        refs = obj._links.get(self.name)
        result = _batch_resolve(refs, self._target_cls()) if refs else []
        # This is a NON-data descriptor (no __set__), so an entry in the
        # instance __dict__ shadows it: after the first read, access is a
        # plain C-level dict lookup that never re-enters Python. Writes go
        # through LinkedModel.__setattr__, which invalidates the entry.
        obj.__dict__[self.name] = result
        return result

    def set_raw(self, obj: object, value: Any) -> None:
        obj.__dict__.pop(self.name, None)  # invalidate the cached read
        if value is None:
            obj._links[self.name] = []
            return
        target = self._target_cls()
        obj._links[self.name] = [_to_ref(v, target) for v in value]

    def refs(self, obj: object) -> List[Ref]:
        """The unresolved reference objects (no backend call)."""
        return list(obj._links.get(self.name, []))

    def iris(self, obj: object) -> List[str]:
        return [r.iri for r in obj._links.get(self.name, []) if r.iri]

    async def aresolve(self, obj: object) -> List[T]:
        """Async resolution handle (backends here are sync)."""
        return self.__get__(obj)


class Link(Generic[T]):
    """Data descriptor for a to-one ``x-oold-range`` link. Reads as ``Optional[T]``."""

    many = False

    def __init__(self, target: "type[T] | str"):
        self._target = target
        self.name: Optional[str] = None
        self.owner: Optional[type] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name
        self.owner = owner

    def _target_cls(self) -> Any:
        return _resolve_target(self._target, self.owner)

    @overload
    def __get__(self, obj: None, objtype: Any = None) -> "Link[T]":
        ...

    @overload
    def __get__(self, obj: object, objtype: Any = None) -> Optional[T]:
        ...

    def __get__(self, obj: Any, objtype: Any = None) -> Any:
        if obj is None:
            return self
        ref = obj._links.get(self.name)
        result = None if ref is None else _batch_resolve([ref], self._target_cls())[0]
        # see LinkList.__get__: non-data descriptor plus instance-dict cache
        obj.__dict__[self.name] = result
        return result

    def set_raw(self, obj: object, value: Any) -> None:
        obj.__dict__.pop(self.name, None)  # invalidate the cached read
        obj._links[self.name] = (
            None if value is None else _to_ref(value, self._target_cls())
        )

    def ref(self, obj: object) -> Optional[Ref]:
        return obj._links.get(self.name)

    def iris(self, obj: object) -> Optional[str]:
        ref = obj._links.get(self.name)
        return ref.iri if ref is not None else None

    async def aresolve(self, obj: object) -> Optional[T]:
        return self.__get__(obj)


_LinkDescr = (Link, LinkList)


class LinkedModel(BaseModel):
    """Base model with transparent, descriptor-based range binding."""

    model_config = ConfigDict(ignored_types=_LinkDescr)

    _links: Dict[str, Any] = PrivateAttr(default_factory=dict)
    __link_fields__: ClassVar[Dict[str, Any]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        fields: Dict[str, Any] = {}
        for base in reversed(cls.__mro__):
            for key, value in vars(base).items():
                if isinstance(value, _LinkDescr):
                    fields[key] = value
        cls.__link_fields__ = fields

    def __init__(self, **data: Any) -> None:
        link_fields = type(self).__link_fields__
        link_data = {k: data.pop(k) for k in list(data) if k in link_fields}
        super().__init__(**data)
        for key, value in link_data.items():
            link_fields[key].set_raw(self, value)

    def __setattr__(self, name: str, value: Any) -> None:
        # Targeted: only link names are intercepted; all other attribute writes
        # go straight to pydantic. Reads are never intercepted (the descriptor
        # handles link reads natively, plain fields stay native).
        descr = type(self).__link_fields__.get(name)
        if descr is not None:
            descr.set_raw(self, value)
        else:
            super().__setattr__(name, value)

    def get_iri(self) -> Optional[str]:
        return getattr(self, "id", None)

    @model_serializer(mode="wrap")
    def _serialize_links(self, handler: Any) -> Dict[str, Any]:
        d = handler(self)
        for name, descr in type(self).__link_fields__.items():
            iris = descr.iris(self)
            if iris:
                d[name] = iris
        return d

    def link_iris(self, name: str) -> Any:
        """The stored IRI(s) for a link field, without resolving."""
        return type(self).__link_fields__[name].iris(self)

    @classmethod
    def ld_context(cls) -> dict:
        return {"id": "@id", "type": "@type"}

    def to_jsonld(self) -> dict:
        return {"@context": self.ld_context(), **self.model_dump(exclude_none=True)}


# Demo models mirroring the user's `knows: list[Person]` example.


class Person(LinkedModel):
    id: str
    name: Optional[str] = None
    # Unannotated descriptors: not pydantic fields. Static type of `p.knows` is
    # `list[Person]`, of `p.best_friend` is `Optional[Person]`.
    knows = LinkList["Person"]("Person")
    best_friend = Link["Person"]("Person")

    @classmethod
    def ld_context(cls) -> dict:
        return {
            "ex": "https://example.org/",
            "id": "@id",
            "type": "@type",
            "name": "ex:name",
            "knows": {"@id": "ex:knows", "@type": "@id"},
            "best_friend": {"@id": "ex:bestFriend", "@type": "@id"},
        }


def demo() -> None:  # pragma: no cover - manual smoke run
    from oold.backend.document_store import SimpleDictDocumentStore
    from oold.backend.interface import SetResolverParam, set_resolver

    store = SimpleDictDocumentStore()
    store.store_json_dicts(
        {
            "ex:p2": {"id": "ex:p2", "name": "Bob"},
            "ex:p3": {"id": "ex:p3", "name": "Carol"},
        }
    )
    set_resolver(SetResolverParam(iri="ex", resolver=store))

    p = Person(id="ex:p1", name="Alice", knows=["ex:p2", "ex:p3"])
    print("knows[0] is a real Person:", isinstance(p.knows[0], Person))
    print("knows[0].name:", p.knows[0].name)
    print("dump:", p.model_dump(exclude_none=True))


if __name__ == "__main__":  # pragma: no cover
    demo()
