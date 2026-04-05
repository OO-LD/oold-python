import json
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    TypeVar,
    Union,
    overload,
)

import pydantic
from pydantic.v1 import BaseModel, PrivateAttr
from typing_extensions import Self, get_args

from oold.backend import interface
from oold.backend.interface import (
    Condition,
    GetBackendParam,
    GetResolverParam,
    Query,
    QueryParam,
    ResolveParam,
    Resolver,
    StoreParam,
    apply_operator,
    get_backend,
    get_resolver,
)
from oold.static import (
    GenericLinkedBaseModel,
    export_jsonld,
    import_json,
    import_jsonld,
)

if TYPE_CHECKING:
    from pydantic.v1.typing import AbstractSetIntStr, MappingIntStrAny

# monkey patching pydantic v1 FieldInfo
import pydantic.v1.fields
from pydantic.v1.fields import FieldInfo


class OOFieldInfo(FieldInfo):
    """Extension of pydantic v1 FieldInfo that restores hashability.
    Pydantic v1's FieldInfo is hashable via object.__hash__, but subclassing
    with custom __eq__ would break that. We keep __hash__ = id(self) to
    prevent TypeError in typing.Union / Annotated metadata processing."""

    def __hash__(self):
        return id(self)


pydantic.v1.fields.FieldInfo = OOFieldInfo


class FieldProxy:
    """Returned by metaclass __getattribute__ for class-level field access.
    Supports comparison operators for query syntax (Entity.name == "test")
    and forwards attribute access / truthiness to the field's default value."""

    __slots__ = ("_default", "name", "parent")

    def __init__(self, default, name, parent):
        object.__setattr__(self, "_default", default)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "parent", parent)

    def __eq__(self, other):
        return Condition(field=self.name, operator="eq", value=other)

    def __ne__(self, other):
        return Condition(field=self.name, operator="ne", value=other)

    def __lt__(self, other):
        return Condition(field=self.name, operator="lt", value=other)

    def __le__(self, other):
        return Condition(field=self.name, operator="le", value=other)

    def __gt__(self, other):
        return Condition(field=self.name, operator="gt", value=other)

    def __ge__(self, other):
        return Condition(field=self.name, operator="ge", value=other)

    def __hash__(self):
        return id(self)

    def __bool__(self):
        d = object.__getattribute__(self, "_default")
        if d is None or d is ...:
            return False
        return bool(d)

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_default")
        if d is not None and d is not ...:
            return getattr(d, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )


# pydantic v1
_types: Dict[str, pydantic.v1.main.ModelMetaclass] = {}


M = TypeVar("M", bound="LinkedBaseModel")


# pydantic v1
class LinkedBaseModelMetaClass(pydantic.v1.main.ModelMetaclass):
    _constructing: bool = False
    """Guards against __getattribute__ intercepting field access during class
    construction. Pydantic checks ``getattr(base, field_name, None)`` in its
    metaclass __new__ to detect shadowed BaseModel attributes. Without this
    flag our __getattribute__ override would return a truthy FieldInfo instead
    of the default None, causing false-positive field-name collision errors."""

    def __new__(mcs, name, bases, namespace):
        LinkedBaseModelMetaClass._constructing = True
        try:
            cls = super().__new__(mcs, name, bases, namespace)
        finally:
            LinkedBaseModelMetaClass._constructing = False

        if hasattr(cls, "get_cls_iri"):
            iri = cls.get_cls_iri()
            if iri is not None:
                if isinstance(iri, list):
                    for i in iri:
                        _types[i] = cls
                else:
                    _types[iri] = cls
        return cls

    # override operators, see https://docs.python.org/3/library/operator.html

    if not TYPE_CHECKING:

        def __getattribute__(self, name):
            if type(self)._constructing:
                return super().__getattribute__(name)
            if name not in ["__bases__", "__fields__", "__dict__"]:
                if (
                    name not in self.__dict__
                    and hasattr(self, "__fields__")
                    and name in self.__fields__
                ):
                    field = self.__fields__[name]
                    return FieldProxy(field.default, name, self)
                else:
                    return super().__getattribute__(name)
            return super().__getattribute__(name)

    @overload
    def __getitem__(cls: type[M], item: str) -> M:
        """Get a class instance by its IRI."""
        ...

    @overload
    def __getitem__(
        cls: type[M], item: List[str]
    ) -> Union[M, "LinkedBaseModelList[M]"]:
        """Get multiple class instances by their IRIs."""
        ...

    @overload
    def __getitem__(
        cls: type[M], item: Union[Query, Condition, bool]
    ) -> Union[M, "LinkedBaseModelList[M]"]:
        """Get class instances matching a query."""
        ...

    def __getitem__(
        cls: type[M], item: Union[str, List[str], Query, Condition, bool]
    ) -> Union[M, "LinkedBaseModelList[M]", Optional["LinkedBaseModelList[M]"]]:
        """Select instances of the class by IRI or by query."""
        return cls.oold_query(item)

    def __setitem__(cls: type[M], key, value: type[M]):
        value._store()


T = TypeVar("T")


class LinkedBaseModelList(Generic[T], List[Optional[T]]):
    """Extension of list that tracks changes to the list
    by syncing every modification with the __iri__ field of the parent model."""

    def __init__(
        self, *args: Optional[T], _synced_iri_list: Optional[List[str]] = None
    ):
        super().__init__(*args)
        self._synced_iri_list = _synced_iri_list
        if self._synced_iri_list is not None:
            self._synced_list = args[0]
            self._synced_iri_list.extend(
                item.get_iri()
                for item in self
                if item is not None and item.get_iri() not in self._synced_iri_list
            )

    def append(self, item: Optional[T]) -> None:
        if self._synced_iri_list is not None:
            self._synced_iri_list.append(item.get_iri())
            self._synced_list.append(item)
        super().append(item)

    def remove(self, item: Optional[T]) -> None:
        if self._synced_iri_list is not None:
            self._synced_iri_list.remove(item.get_iri())
            self._synced_list.remove(item)
        super().remove(item)

    def extend(self, iterable):
        if self._synced_iri_list is not None:
            self._synced_iri_list.extend(
                item.get_iri() for item in iterable if item is not None
            )
            self._synced_list.extend(iterable)
        return super().extend(iterable)

    def get_item_type(self):
        if hasattr(self, "__orig_class__"):
            return get_args(self.__orig_class__)[0]
        return None

    # override [] operator to also support string indices

    @overload
    def __getitem__(self, index: str) -> Optional[Union[T, "LinkedBaseModelList[T]"]]:
        ...

    @overload
    def __getitem__(self, index: bool) -> Optional[Union[T, "LinkedBaseModelList[T]"]]:
        ...

    @overload
    def __getitem__(self, index: int) -> Optional[T]:
        ...

    # allow pandas-style queries, e.g. l[Entity.name=='John']
    @overload
    def __getitem__(
        self, index: Union[Query, Condition, bool]
    ) -> Optional[Union[T, "LinkedBaseModelList[T]"]]:
        ...

    def __getitem__(self, index):
        if isinstance(index, str):
            if index.startswith("@"):
                # query, e.g. "@name=='John'"
                key = index[1:].split("==")[0].strip()
                value = index.split("==")[1].strip("'\"")
                return LinkedBaseModelList[self.get_item_type()](
                    [
                        item
                        for item in self
                        if item and getattr(item, key, None) == value
                    ],
                    _synced_iri_list=self._synced_iri_list,
                )
            else:
                # IRI lookup
                for item in self:
                    if item and item.get_iri() == index:
                        return item
                raise KeyError(f"No item with IRI {index} found")
        elif isinstance(index, Condition):
            key = index.field
            op = index.operator
            value = index.value
            return LinkedBaseModelList[self.get_item_type()](
                [
                    item
                    for item in self
                    if item and apply_operator(op, getattr(item, key, None), value)
                ],
                _synced_iri_list=self._synced_iri_list,
            )
        elif isinstance(index, Query):
            raise NotImplementedError("Query-based indexing not implemented yet")
        else:
            return super().__getitem__(index)

    def __getattribute__(self, name):
        if not name == "__orig_class__":
            if self is not None and hasattr(self, "__orig_class__"):
                _type = get_args(self.__orig_class__)[0]
                if name in _type.__fields__.keys():
                    result_list = LinkedBaseModelList[_type]([], _synced_iri_list=None)
                    for item in self:
                        if item is not None and hasattr(item, name):
                            value = getattr(item, name)
                            if isinstance(value, list):
                                result_list.extend(value)
                            else:
                                result_list.append(value)
                    return result_list
        return super().__getattribute__(name)


# the following switch ensures that autocomplete works in IDEs like VSCode
if TYPE_CHECKING:

    class _LinkedBaseModel(BaseModel, GenericLinkedBaseModel):
        pass

else:

    class _LinkedBaseModel(
        BaseModel, GenericLinkedBaseModel, metaclass=LinkedBaseModelMetaClass
    ):
        pass


class LinkedBaseModel(_LinkedBaseModel):
    """LinkedBaseModel for pydantic v1"""

    __iris__: Optional[Dict[str, Union[str, List[str]]]] = PrivateAttr()

    @classmethod
    def get_cls_iri(cls) -> Union[str, List[str], None]:
        """Return the unique IRI of the class.
        Overwrite this method in the subclass."""
        schema = {}
        # pydantic v1
        if hasattr(cls, "__config__"):
            if hasattr(cls.__config__, "schema_extra"):
                schema = cls.__config__.schema_extra

        cls_iri = []
        # schema annotation - should be expanded IRI
        if "$id" in schema:
            cls_iri.append(schema["$id"])
        elif "iri" in schema:
            cls_iri.append(schema["iri"])
        # default value of type field - may be compacted IRI
        type_field_name = cls.get_type_field()
        # pydantic v2
        type_field = cls.__fields__.get(type_field_name, None)
        if type_field is not None:
            cls_iri.append(type_field.default)
        if len(cls_iri) == 0:
            return None
        elif len(cls_iri) == 1:
            return cls_iri[0]
        else:
            return cls_iri

    def get_iri(self) -> str:
        """Return the unique IRI of the object.
        Overwrite this method in the subclass."""
        return self.id

    @classmethod
    def parse_obj(cls, obj: Any) -> "LinkedBaseModel":
        """Parse the object and return a LinkedBaseModel instance.
        This method is called by pydantic when creating
        a new (default) instance of the model."""
        if isinstance(obj, str):
            # pydantic v1
            return cls._resolve([obj])[obj]
        if isinstance(obj, list):
            # pydantic v1
            # return cls._resolve(obj).nodes[obj[0]]
            node_dict = cls._resolve(obj)
            node_list = []
            for iri in obj:
                node = node_dict[iri]
                if node:
                    node_list.append(node)
            return node_list
        elif isinstance(obj, dict):
            return super().parse_obj(obj)

    def __init__(self, *a, **kw):
        if "__iris__" not in kw:
            kw["__iris__"] = {}

        for name in list(kw):  # force copy of keys for inline-delete
            # print(name)
            if name == "__iris__":
                continue
            # rewrite <attr> to <attr>_iri
            # pprint(self.__fields__)
            extra = None
            # pydantic v1
            if name in self.__fields__:
                if hasattr(self.__fields__[name].default, "json_schema_extra"):
                    extra = self.__fields__[name].default.json_schema_extra
                elif hasattr(self.__fields__[name].field_info, "extra"):
                    extra = self.__fields__[name].field_info.extra
            # pydantic v2
            # extra = self.model_fields[name].json_schema_extra

            if extra and "range" in extra:
                arg_is_list = isinstance(kw[name], list)

                # annotation_is_list = False
                # args = self.model_fields[name].annotation.__args__
                # if hasattr(args[0], "_name"):
                #    is_list = args[0]._name == "List"
                if arg_is_list:
                    kw["__iris__"][name] = []
                    for e in kw[name][:]:  # interate over copy of list
                        if isinstance(e, BaseModel):  # contructed with object ref
                            kw["__iris__"][name].append(e.get_iri())
                        elif isinstance(e, str):  # constructed from json
                            kw["__iris__"][name].append(e)
                            kw[name].remove(e)  # remove to construct valid instance
                    if len(kw[name]) == 0:
                        # pydantic v1
                        kw[name] = None  # else pydantic v1 will set a FieldInfo object
                        # pydantic v2
                        # del kw[name]
                else:
                    if isinstance(kw[name], BaseModel):  # contructed with object ref
                        # print(kw[name].id)
                        kw["__iris__"][name] = kw[name].get_iri()
                    elif isinstance(kw[name], str):  # constructed from json
                        kw["__iris__"][name] = kw[name]
                        # pydantic v1
                        kw[name] = None  # else pydantic v1 will set a FieldInfo object
                        # pydantic v2
                        # del kw[name]

        BaseModel.__init__(self, *a, **kw)
        # handle default values
        for name in list(self.__dict__.keys()):
            if self.__dict__[name] is None:
                continue
            extra = None
            # pydantic v1
            if name in self.__fields__:
                if hasattr(self.__fields__[name].default, "json_schema_extra"):
                    extra = self.__fields__[name].default.json_schema_extra
                elif hasattr(self.__fields__[name].field_info, "extra"):
                    extra = self.__fields__[name].field_info.extra
            if extra and "range" in extra and name not in kw["__iris__"]:
                arg_is_list = isinstance(self.__dict__[name], list)

                if arg_is_list:
                    kw["__iris__"][name] = []
                    for e in self.__dict__[name]:
                        if isinstance(e, BaseModel):  # contructed with object ref
                            kw["__iris__"][name].append(e.get_iri())
                else:
                    # contructed with object ref
                    if isinstance(self.__dict__[name], BaseModel):
                        kw["__iris__"][name] = self.__dict__[name].get_iri()

        self.__iris__ = kw["__iris__"]

        # iterate over all fields
        # if x-oold-required-iri occurs in extra and the field is not set in __iri__
        # throw an error
        for name in self.__fields__:
            extra = None
            # pydantic v1
            if name in self.__fields__:
                if hasattr(self.__fields__[name].default, "json_schema_extra"):
                    extra = self.__fields__[name].default.json_schema_extra
                elif hasattr(self.__fields__[name].field_info, "extra"):
                    extra = self.__fields__[name].field_info.extra
            # pydantic v2
            # extra = self.model_fields[name].json_schema_extra

            if extra and "x_oold_required_iri" in extra:
                if name not in self.__iris__:
                    raise ValueError(f"{name} is required but not set")

    def _handle_value(self, name, value):
        extra = None
        # pydantic v1
        if name in self.__fields__:
            if hasattr(self.__fields__[name].default, "json_schema_extra"):
                extra = self.__fields__[name].default.json_schema_extra
            elif hasattr(self.__fields__[name].field_info, "extra"):
                extra = self.__fields__[name].field_info.extra
        # pydantic v2
        # extra = self.model_fields[name].json_schema_extra

        if extra and "range" in extra:
            arg_is_list = isinstance(value, list)

            if arg_is_list:
                self.__iris__[name] = []
                for e in value[:]:  # interate over copy of list
                    if isinstance(e, BaseModel):  # contructed with object ref
                        self.__iris__[name].append(e.get_iri())
                    elif isinstance(e, str):  # constructed from json
                        self.__iris__[name].append(e)
                        value.remove(e)  # remove to construct valid instance
                if len(value) == 0:
                    # pydantic v1
                    value = None  # else pydantic v1 will set a FieldInfo object
                    # pydantic v2
                    # del kw[name]
            else:
                if isinstance(value, BaseModel):  # contructed with object ref
                    # print(value.id)
                    self.__iris__[name] = value.get_iri()
                elif isinstance(value, str):  # constructed from json
                    self.__iris__[name] = value
                    # pydantic v1
                    value = None  # else pydantic v1 will set a FieldInfo object
                    # pydantic v2
                    # del kw[name]
                elif value is None:
                    del self.__iris__[name]
        return value

    def __setattr__(self, name, value, internal=False):
        # print("__setattr__", name, value)
        if not internal and name not in [
            "__dict__",
            "__pydantic_private__",
            "__iris__",
        ]:
            value = self._handle_value(name, value)

        return super().__setattr__(name, value)

    def __getattribute__(self, name):
        # print("__getattribute__ ", name)
        # async? https://stackoverflow.com/questions/33128325/
        # how-to-set-class-attribute-with-await-in-init

        if name in ["__dict__", "__pydantic_private__", "__iris__"]:
            return BaseModel.__getattribute__(self, name)  # prevent loop

        else:
            if hasattr(self, "__iris__"):
                if name in self.__iris__ and len(self.__iris__[name]) > 0:
                    if self.__dict__[name] is None or (
                        isinstance(self.__dict__[name], list)
                        and len(self.__dict__[name]) == 0
                    ):
                        iris = self.__iris__[name]
                        is_list = isinstance(iris, list)
                        if not is_list:
                            iris = [iris]

                        node_dict = self._resolve(iris)
                        if is_list:
                            node_list = []
                            for iri in iris:
                                node = node_dict[iri]
                                node_list.append(node)
                            self.__setattr__(name, node_list, True)
                        else:
                            node = node_dict[iris[0]]
                            if node:
                                self.__setattr__(name, node, True)

        result = BaseModel.__getattribute__(self, name)
        if isinstance(result, list) and name in self.__iris__:
            result = LinkedBaseModelList[type(self)](
                result, _synced_iri_list=self.__iris__[name]
            )
        return result

    def get_iri_ref(self, field_name: str):
        """Return the stored IRI reference string(s) for a field without
        triggering resolution.

        Parameters
        ----------
        field_name
            The name of the field to retrieve the IRI reference for.

        Returns
        -------
            A string IRI, a list of string IRIs, or ``None`` if no IRI is
            stored for the given field.
        """
        iris = self.__iris__.get(field_name)
        if iris is None:
            return None
        if isinstance(iris, list):
            return iris if iris else None
        return iris

    def get_raw(self, field_name: str):
        """Return the raw value of a field without triggering IRI resolution.

        Unlike normal attribute access which may trigger network calls to
        resolve IRI references, this returns the Python object as stored
        internally (``None`` for unresolved IRIs, the model instance if
        already resolved, or a plain value for non-IRI fields).

        Parameters
        ----------
        field_name
            The name of the field to retrieve.

        Returns
        -------
            The raw field value, or ``None`` if the field is unresolved or
            does not exist.
        """
        return self.__dict__.get(field_name)

    @staticmethod
    def _resolve(iris):
        resolver = get_resolver(GetResolverParam(iri=iris[0])).resolver
        node_dict = resolver.resolve(
            ResolveParam(iris=iris, model_cls=LinkedBaseModel)
        ).nodes
        return node_dict

    def _store(self):
        backend = get_backend(GetBackendParam(iri=self.get_iri())).backend
        backend.store(StoreParam(nodes={self.get_iri(): self}))

    def store_jsonld(self):
        """Store the model instance in a backend matching its IRI."""
        self._store()

    @classmethod
    def _oold_query(
        cls, query: Union[str, List[str], Query, Condition]
    ) -> "LinkedBaseModelList[Self]":
        # get all resolvers
        resolvers: List[Resolver] = interface._resolvers.values()
        node_list = []
        for r in resolvers:
            try:
                if isinstance(query, (str, list)):
                    _node_list = r.resolve(
                        ResolveParam(
                            iris=[query] if isinstance(query, str) else query,
                            model_cls=cls,
                        )
                    ).nodes.values()
                else:
                    _node_list = r.query(
                        QueryParam(query=query, model_cls=cls)
                    ).nodes.values()
                node_list.extend(_node_list)
            except NotImplementedError:
                continue

        if isinstance(query, str):
            return node_list[0] if len(node_list) > 0 else None
        else:
            return (
                LinkedBaseModelList[Self](node_list, _synced_iri_list=None)
                if len(node_list) > 0
                else None
            )

    @overload
    @classmethod
    def oold_query(cls, item: str) -> Self:
        ...

    @overload
    @classmethod
    def oold_query(cls, item: List[str]) -> "LinkedBaseModelList[Self]":
        ...

    @overload
    @classmethod
    def oold_query(
        cls, item: Union[Query, Condition, bool]
    ) -> Optional["LinkedBaseModelList[Self]"]:
        ...

    @classmethod
    def oold_query(
        cls, item: Union[str, List[str], Query, bool]
    ) -> Union[
        Self, "LinkedBaseModelList[Self]", Optional["LinkedBaseModelList[Self]"]
    ]:
        """Allow access to the class by its IRI."""
        return cls._oold_query(item)

    @staticmethod
    def _recursive_object_to_iri(d: dict, model_obj):
        """Recursively apply __iris__ replacement for nested model objects."""
        for name, value in list(d.items()):
            if name not in model_obj.__fields__:
                continue
            # Access raw value without triggering IRI resolution
            model_value = model_obj.__dict__.get(name)
            if isinstance(value, list) and isinstance(model_value, list):
                for i, (item, model_item) in enumerate(zip(value, model_value)):
                    if isinstance(item, dict) and hasattr(model_item, "__iris__"):
                        model_item._object_to_iri(item)
                        LinkedBaseModel._recursive_object_to_iri(item, model_item)
            elif isinstance(value, dict) and hasattr(model_value, "__iris__"):
                model_value._object_to_iri(value)
                LinkedBaseModel._recursive_object_to_iri(value, model_value)

    # pydantic v1
    def json(
        self,
        *,
        include: Optional[Union["AbstractSetIntStr", "MappingIntStrAny"]] = None,
        exclude: Optional[Union["AbstractSetIntStr", "MappingIntStrAny"]] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        encoder: Optional[Callable[[Any], Any]] = None,
        models_as_dict: bool = True,
        **dumps_kwargs: Any,
    ) -> str:
        """
        Generate a JSON representation of the model,
        `include` and `exclude` arguments as per `dict()`.

        `encoder` is an optional function to supply as `default` to json.dumps(),
        other arguments as per `json.dumps()`.
        """
        d = json.loads(
            BaseModel.json(
                self,
                include=include,
                exclude=exclude,
                by_alias=by_alias,
                skip_defaults=skip_defaults,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=False,  # handle None values separately
                encoder=encoder,
                models_as_dict=models_as_dict,
                **dumps_kwargs,
            )
        )  # ToDo directly use dict?
        # this may replace some None values with IRIs in case they were never resolved
        # thats why we handle exclude_none there
        self._object_to_iri(d)
        # Recursively apply _object_to_iri for nested models
        self._recursive_object_to_iri(d, self)
        if exclude_none:
            d = self.remove_none(d)
        return json.dumps(d, **dumps_kwargs)

    def to_jsonld(self) -> Dict:
        """Return the RDF representation of the object as JSON-LD."""
        return export_jsonld(self, BaseModel)

    @classmethod
    def from_jsonld(cls, jsonld: Dict) -> "LinkedBaseModel":
        """Constructs a model instance from a JSON-LD representation."""
        return import_jsonld(BaseModel, LinkedBaseModel, cls, jsonld, _types)

    def to_json(self) -> Dict:
        """Return the JSON representation of the object as dict."""
        return json.loads(self.json(exclude_none=True))

    @classmethod
    def from_json(cls, json_dict: Dict) -> "LinkedBaseModel":
        """Constructs a model instance from a JSON representation."""
        return import_json(BaseModel, LinkedBaseModel, cls, json_dict, _types)
