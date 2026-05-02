import json
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
    overload,
)

import pydantic

# monkey patching pydantic FieldInfo
import pydantic.fields
from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined, core_schema
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


class OOFieldInfo(FieldInfo):
    """Extension of pydantic FieldInfo that restores hashability.
    Pydantic's FieldInfo is hashable via object.__hash__, but subclassing
    with custom __eq__ would break that. We keep __hash__ = id(self) to
    prevent TypeError in typing.Union / Annotated metadata processing."""

    def __hash__(self):
        return id(self)


pydantic.fields.FieldInfo = OOFieldInfo


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
        if d is None or d is PydanticUndefined:
            return False
        return bool(d)

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_default")
        if d is not None and d is not PydanticUndefined:
            return getattr(d, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )


# pydantic v2
_types: Dict[str, pydantic.main._model_construction.ModelMetaclass] = {}


M = TypeVar("M", bound="LinkedBaseModel")


# pydantic v2
class LinkedBaseModelMetaClass(pydantic.main._model_construction.ModelMetaclass):
    _constructing: bool = False
    """Guards against __getattribute__ intercepting field access during class
    construction. Pydantic checks ``getattr(base, field_name, None)`` in its
    metaclass __new__ to detect shadowed BaseModel attributes. Without this
    flag our __getattribute__ override would return a truthy FieldInfo instead
    of the default None, causing false-positive field-name collision errors."""

    def __new__(mcs, name, bases, namespace, **kwargs):
        LinkedBaseModelMetaClass._constructing = True
        try:
            cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        finally:
            LinkedBaseModelMetaClass._constructing = False

        # Register type IRI mapping, but skip controller classes
        # (they extend data models but should not replace them in
        # the type lookup table).
        _is_ctrl = any(
            b.__module__ == "oold.model" and b.__name__ == "BaseController"
            for b in cls.__mro__
        )
        if _is_ctrl:
            pass
        elif hasattr(cls, "get_cls_iri"):
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
            # print(f"Accessing attribute {name}")
            if type(self)._constructing:
                return super().__getattribute__(name)
            if name not in [
                "__bases__",
                "model_fields",
                "__pydantic_fields__",
                "__dict__",
            ]:
                # if name not in ["model_fields"]:
                # check if attribute is in fields
                if (
                    name not in self.__dict__  # prevent shadowing if default value
                    and hasattr(self, "model_fields")
                    and name in self.model_fields
                ):
                    # private_attributes = self.__dict__.get('__private_attributes__')
                    # if private_attributes and name in private_attributes:
                    #     return super().__getattribute__(name)
                    # print(f"Attribute {name} is in model fields")
                    # ToDo: lookup the fields property if available
                    # return Condition(field=name)
                    field_info = self.model_fields[name]
                    return FieldProxy(field_info.default, name, self)
                    # f = super().__getattribute__(name)
                    # return f
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
        # note: type M is to blend in M attributes
        # in the signature of LinkedBaseModelList[M]
        ...

    @overload
    def __getitem__(
        cls: type[M], item: Union[Query, Condition, bool]
    ) -> Union[M, "LinkedBaseModelList[M]"]:
        """Get class instances matching a query."""
        # note: (Entity.name == "test") is interpreted as bool
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
    """Extension of list that tracks changes to the list.
    by syncing every modification with the __iri__ field of the parent model."""

    def __init__(
        self, *args: Optional[T], _synced_iri_list: Optional[List[str]] = None
    ):
        super().__init__(*args)
        self._synced_iri_list = (
            _synced_iri_list  # if _synced_iri_list is not None else []
        )
        # self._synced_iri_list.extend(
        #     item.get_iri() for item in self if item is not None
        # )
        # initialize the synced_iri_list with the IRIs of the initial items in the list
        if self._synced_iri_list is not None:
            self._synced_list = args[0]
            self._synced_iri_list.extend(
                item.get_iri()
                for item in self
                if item is not None and item.get_iri() not in self._synced_iri_list
            )

    # def _set_synced_iri_list(self, iri_list: List[str]) -> None:
    #     """Set the list of IRIs that are synced with the linked data store."""
    #     self._synced_iri_list = iri_list

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        instance_schema = core_schema.is_instance_schema(cls)

        args = get_args(source)
        if args:
            # replace the type and rely on Pydantic to generate the right schema
            # for `Sequence`
            sequence_t_schema = handler.generate_schema(List[args[0]])
        else:
            sequence_t_schema = handler.generate_schema(List)

        non_instance_schema = core_schema.no_info_after_validator_function(
            LinkedBaseModelList, sequence_t_schema
        )
        return core_schema.union_schema([instance_schema, non_instance_schema])

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
        # Returns the actual type argument, e.g. Entity
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
            # if name == "links":
            #    print(typing.get_args(self))
            if self is not None and hasattr(self, "__orig_class__"):
                _type = get_args(self.__orig_class__)[0]
                if name in _type.model_fields.keys():
                    # print(f"Attribute {name} is in type {_type}")
                    # build a new LinkedBaseModelList with all
                    # the values of this attribute
                    # if attribute is List
                    result_list = LinkedBaseModelList[_type]([], _synced_iri_list=None)
                    for item in self:
                        if item is not None and hasattr(item, name):
                            value = getattr(item, name)
                            if isinstance(value, list):
                                result_list.extend(value)
                            else:
                                result_list.append(value)
                    return result_list

        # else:
        return super().__getattribute__(name)


# the following switch ensures that autocomplete works in IDEs like VSCode
# if TYPE_CHECKING:

#     class _LinkedBaseModel(BaseModel, GenericLinkedBaseModel):
#         pass

# else:

#     class _LinkedBaseModel(
#         BaseModel, GenericLinkedBaseModel, metaclass=LinkedBaseModelMetaClass
#     ):
#         pass


# class LinkedBaseModel(_LinkedBaseModel):
class LinkedBaseModel(
    BaseModel, GenericLinkedBaseModel, metaclass=LinkedBaseModelMetaClass
):
    """LinkedBaseModel for pydantic v2"""

    __iris__: Optional[Dict[str, Union[str, List[str]]]] = {}

    @classmethod
    def get_cls_iri(cls) -> Union[str, List[str], None]:
        """Return the unique IRI of the class.
        Overwrite this method in the subclass."""
        schema = {}
        # pydantic v2
        if hasattr(cls, "model_config"):
            if "json_schema_extra" in cls.model_config:
                schema = cls.model_config["json_schema_extra"]

        cls_iri = []
        # schema annotation - should be expanded IRI
        if "$id" in schema:
            cls_iri.append(schema["$id"])
        elif "iri" in schema:
            cls_iri.append(schema["iri"])
        # default value of type field - may be compacted IRI
        type_field_name = cls.get_type_field()
        # pydantic v2
        type_field = cls.model_fields.get(type_field_name, None)
        if type_field is not None and type_field.default not in cls_iri:
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
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: Union[bool, None] = None,
        from_attributes: Union[bool, None] = None,
        context: Union[Any, None] = None,
    ) -> Self:
        """Validate a pydantic model instance.

        Args:
            obj: The object to validate.
            strict: Whether to enforce types strictly.
            from_attributes: Whether to extract data from object attributes.
            context: Additional context to pass to the validator.

        Raises:
            ValidationError: If the object could not be validated.

        Returns:
            The validated model instance.
        """
        if isinstance(obj, str):
            return cls._resolve([obj])[obj]
        if isinstance(obj, list):
            node_dict = cls._resolve(obj)
            node_list = []
            for iri in obj:
                node = node_dict[iri]
                if node:
                    node_list.append(node)
            return node_list
        elif isinstance(obj, dict):
            super().model_validate(
                obj, strict=strict, from_attributes=from_attributes, context=context
            )

    def __init__(self, *a, **kw):
        # Accept a model instance as first positional arg:
        # TargetModel(source_model, extra_field=value)
        if a and isinstance(a[0], BaseModel):
            result = a[0].cast(type(self), **kw)
            kw = result.model_dump()
            kw["__iris__"] = getattr(result, "__iris__", {})
            a = ()

        if "__iris__" not in kw:
            kw["__iris__"] = {}

        for name in list(kw):  # force copy of keys for inline-delete
            if name == "__iris__":
                continue
            if name not in self.model_fields:
                continue
            # rewrite <attr> to <attr>_iri
            # pprint(self.__fields__)
            extra = None
            # pydantic v1
            # if name in self.__fields__:
            #     if hasattr(self.__fields__[name].default, "json_schema_extra"):
            #         extra = self.__fields__[name].default.json_schema_extra
            #     elif hasattr(self.__fields__[name].field_info, "extra"):
            #         extra = self.__fields__[name].field_info.extra
            # pydantic v2
            extra = self.model_fields[name].json_schema_extra

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
                        # kw[name] = None # else pydantic v1 will set a FieldInfo object
                        # pydantic v2
                        kw[name] = None  # else default value may be set
                else:
                    if isinstance(kw[name], BaseModel):  # contructed with object ref
                        # print(kw[name].id)
                        kw["__iris__"][name] = kw[name].get_iri()
                    elif isinstance(kw[name], str):  # constructed from json
                        kw["__iris__"][name] = kw[name]
                        # pydantic v1
                        # kw[name] = None # else pydantic v1 will set a FieldInfo object
                        # pydantic v2
                        kw[name] = None  # else default value may be set

        BaseModel.__init__(self, *a, **kw)
        # handle default values
        for name in list(self.__dict__.keys()):
            if self.__dict__[name] is None:
                continue
            extra = None
            # pydantic v1
            # if name in self.__fields__:
            #     if hasattr(self.__fields__[name].default, "json_schema_extra"):
            #         extra = self.__fields__[name].default.json_schema_extra
            #     elif hasattr(self.__fields__[name].field_info, "extra"):
            #         extra = self.__fields__[name].field_info.extra
            # pydantic v2
            extra = self.model_fields[name].json_schema_extra

            if extra and "range" in extra:
                arg_is_list = isinstance(self.__dict__, list)

                if arg_is_list:
                    kw["__iris__"][name] = []
                    for e in self.__dict__[name]:
                        if isinstance(e, BaseModel):  # contructed with object ref
                            kw["__iris__"][name].append(e.get_iri())
                else:
                    if isinstance(
                        self.__dict__[name], BaseModel
                    ):  # contructed with object ref
                        kw["__iris__"][name] = self.__dict__[name].get_iri()

        self.__iris__ = kw["__iris__"]

        # iterate over all fields
        # if x-oold-required-iri occurs in extra and the field is not set in __iri__
        # throw an error
        for name in self.model_fields:
            extra = None
            # pydantic v1
            # if name in self.__fields__:
            #     if hasattr(self.__fields__[name].default, "json_schema_extra"):
            #         extra = self.__fields__[name].default.json_schema_extra
            #     elif hasattr(self.__fields__[name].field_info, "extra"):
            #         extra = self.__fields__[name].field_info.extra
            # pydantic v2
            extra = self.model_fields[name].json_schema_extra

            if extra and "x-oold-required-iri" in extra:
                if name not in self.__iris__:
                    raise ValueError(f"{name} is required but not set")

    def _handle_value(self, name, value):
        extra = None
        # pydantic v1
        # if name in self.__fields__:
        #     if hasattr(self.__fields__[name].default, "json_schema_extra"):
        #         extra = self.__fields__[name].default.json_schema_extra
        #     elif hasattr(self.__fields__[name].field_info, "extra"):
        #         extra = self.__fields__[name].field_info.extra
        # pydantic v2
        extra = self.model_fields[name].json_schema_extra

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

        if name == "model_fields":
            return type(self).model_fields

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

    def model_dump(self, **kwargs):  # extent BaseClass export function
        # print("dict")
        remove_none = kwargs.get("exclude_none", False)
        kwargs["exclude_none"] = False
        d = super().model_dump(**kwargs)
        # pprint(d)
        self._object_to_iri(d)
        self._recursive_object_to_iri(d, self)
        if remove_none:
            d = self.remove_none(d)
        # pprint(d)
        return d

    @staticmethod
    def _recursive_object_to_iri(d: dict, model_obj):
        """Recursively apply __iris__ replacement for nested model objects."""
        for name, value in list(d.items()):
            if name not in model_obj.model_fields:
                continue
            # Access raw value without triggering IRI resolution
            model_value = model_obj.__dict__.get(name)
            if isinstance(value, list) and isinstance(model_value, list):
                for item, model_item in zip(value, model_value):
                    if isinstance(item, dict) and hasattr(model_item, "__iris__"):
                        model_item._object_to_iri(item)
                        LinkedBaseModel._recursive_object_to_iri(item, model_item)
            elif isinstance(value, dict) and hasattr(model_value, "__iris__"):
                model_value._object_to_iri(value)
                LinkedBaseModel._recursive_object_to_iri(value, model_value)

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
        # ToDo: filter resolvers that support this class
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
                # resolver does not support query
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

    # note: (Entity.name == "test") is interpreted as bool
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
        # if isinstance(item, Query):
        #     # resolve all instances of this class
        #     #print(f"Select all {cls.__name__} that match {index}")
        #     #return cls._oold_query(item)
        #     return cls(id="ex:test", name="test")
        # else:
        #     result = cls._resolve(item if isinstance(item, list) else [item])
        #     return (
        #         result[item] if isinstance(item, str)
        #         else LinkedBaseModelList[Self](
        #             [result[i] for i in item]
        #         )
        #     )

    # pydantic v2
    def model_dump_json(
        self,
        *,
        indent: Union[int, None] = None,
        include: Union[pydantic.main.IncEx, None] = None,
        exclude: Union[pydantic.main.IncEx, None] = None,
        context: Union[Any, None] = None,
        by_alias: bool = False,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
        round_trip: bool = False,
        warnings: Union[bool, Literal["none", "warn", "error"]] = True,
        serialize_as_any: bool = False,
        **dumps_kwargs: Any,
    ) -> str:
        """Usage docs:
        https://docs.pydantic.dev/2.10/concepts/serialization/#modelmodel_dump_json

        Generates a JSON representation of the model using Pydantic's `to_json` method.

        Args:
            indent: Indentation to use in the JSON output.
                If None is passed, the output will be compact.
            include: Field(s) to include in the JSON output.
            exclude: Field(s) to exclude from the JSON output.
            context: Additional context to pass to the serializer.
            by_alias: Whether to serialize using field aliases.
            exclude_unset: Whether to exclude fields that have not been explicitly set.
            exclude_defaults: Whether to exclude fields that are set to
                their default value.
            exclude_none: Whether to exclude fields that have a value of `None`.
            round_trip: If True, dumped values should be valid as input
                for non-idempotent types such as Json[T].
            warnings: How to handle serialization errors. False/"none" ignores them,
                True/"warn" logs errors, "error" raises a
                [`PydanticSerializationError`][pydantic_core.PydanticSerializationError].
            serialize_as_any: Whether to serialize fields with duck-typing serialization
                behavior.

        Returns:
            A JSON string representation of the model.
        """
        d = json.loads(
            BaseModel.model_dump_json(
                self,
                indent=indent,
                include=include,
                exclude=exclude,
                context=context,
                by_alias=by_alias,
                exclude_unset=exclude_unset,
                exclude_defaults=exclude_defaults,
                exclude_none=False,  # handle None values separately
                round_trip=round_trip,
                warnings=warnings,
                serialize_as_any=serialize_as_any,
            )
        )  # ToDo directly use dict?
        # this may replace some None values with IRIs in case they were never resolved
        # thats why we handle exclude_none there
        self._object_to_iri(d)
        self._recursive_object_to_iri(d, self)
        if exclude_none:
            d = self.remove_none(d)
        return json.dumps(d, **dumps_kwargs)

    def cast(self, cls, remove_extra=False, silent=True, **kwargs):
        """Cast this instance to a different model class.

        Parameters
        ----------
        cls
            Target class to cast to.
        remove_extra
            If True, drop fields not defined on the target class.
        silent
            If True, suppress warnings about dropped fields.
        kwargs
            Additional fields to set on the new instance.
        """
        data = {**self.model_dump(), **kwargs}
        if remove_extra:
            target_fields = set()
            if hasattr(cls, "model_fields"):
                target_fields = set(cls.model_fields.keys())
            elif hasattr(cls, "__fields__"):
                target_fields = set(cls.__fields__.keys())
            if target_fields:
                extra = [k for k in data if k not in target_fields]
                for k in extra:
                    del data[k]
        if "type" in data:
            del data["type"]
        # Carry over __iris__ (range field references)
        if hasattr(self, "__iris__"):
            iris = dict(self.__iris__)
            if "__iris__" in data:
                iris.update(data["__iris__"])
            data["__iris__"] = iris
        result = cls(**data)
        return result

    def to_jsonld(self) -> Dict:
        """Return the RDF representation of the object as JSON-LD."""
        return export_jsonld(self, BaseModel)

    @classmethod
    def from_jsonld(cls, jsonld: Dict) -> "LinkedBaseModel":
        """Constructs a model instance from a JSON-LD representation."""
        return import_jsonld(BaseModel, LinkedBaseModel, cls, jsonld, _types)

    def to_json(self, exclude_defaults: bool = False) -> Dict:
        """Return the JSON representation of the object.

        Parameters
        ----------
        exclude_defaults
            If True, fields with default values are excluded from the
            output. Useful for compact storage where defaults can be
            re-populated on deserialization via from_json().
        """
        return json.loads(
            self.model_dump_json(
                exclude_none=True,
                exclude_defaults=exclude_defaults,
            )
        )

    @classmethod
    def from_json(cls, data: Dict) -> "LinkedBaseModel":
        """Constructs a model instance from a JSON representation."""
        return import_json(BaseModel, LinkedBaseModel, cls, data, _types)

    # @classmethod
    # def model_json_schema(
    #     cls, by_alias=True, ref_template=...,
    #     schema_generator=..., mode='validation',
    # ) -> dict[str, Any]:
    #     # return super().model_json_schema(
    #     #     by_alias, ref_template, schema_generator, mode
    #     # )
    #     return cls.export_schema(cls)


class BaseController:
    """Base mixin for controllers that extend LinkedBaseModel data classes.

    Overrides to_json() and to_jsonld() to serialize only the pure data
    model fields, stripping controller-only fields (e.g. archive_database,
    auto_archive, connection state).

    The data model class is auto-detected from the MRO: the first
    LinkedBaseModel subclass that is not also a BaseController subclass.

    Controllers are excluded from oold's type IRI registry (_types) so
    they don't replace their pure data model counterparts during
    backend resolution.
    """

    def _get_data_model_cls(self):
        """Auto-detect the pure data model class from the MRO.

        Finds all direct LinkedBaseModel bases that are not controllers.
        If there are multiple, creates a dynamic union class combining
        them (e.g. Controller(ModelA, ModelB) -> _ModelA_ModelB).
        """

        def _is_data_model(cls):
            return (
                cls is not type(self)
                and cls.__name__
                not in (
                    "LinkedBaseModel",
                    "_LinkedBaseModel",
                    "BaseController",
                    "GenericLinkedBaseModel",
                    "BaseModel",
                    "Representation",
                )
                and hasattr(cls, "to_json")
                and hasattr(cls, "from_json")
                and not issubclass(cls, BaseController)
            )

        model_bases = []
        for cls in type(self).__mro__:
            if _is_data_model(cls):
                if not any(issubclass(m, cls) for m in model_bases):
                    model_bases.append(cls)
        if len(model_bases) == 0:
            return None
        if len(model_bases) == 1:
            return model_bases[0]
        name = "_".join(b.__name__ for b in model_bases)
        union_cls = type(name, tuple(model_bases), {})
        union_cls._union_bases = model_bases
        return union_cls

    def _get_model_bases(self):
        """Return the list of pure data model base classes."""
        model_cls = self._get_data_model_cls()
        if model_cls is None:
            return []
        if hasattr(model_cls, "_union_bases"):
            return model_cls._union_bases
        return [model_cls]

    def _collect_type_array(self):
        """Collect merged type array from all pure data model bases."""
        bases = self._get_model_bases()
        if len(bases) <= 1:
            return None
        merged = []
        for base in bases:
            field = None
            if hasattr(base, "model_fields"):
                field = base.model_fields.get("type")
            elif hasattr(base, "__fields__"):
                field = base.__fields__.get("type")
            default = getattr(field, "default", None) if field else None
            if isinstance(default, list):
                for t in default:
                    if t not in merged:
                        merged.append(t)
            elif isinstance(default, str) and default not in merged:
                merged.append(default)
        return merged if merged else None

    def _cast_to_pure(self, model_cls):
        """Cast self to the pure model class."""
        return self.cast(model_cls, remove_extra=True)

    def to_json(self, **kwargs):
        model_cls = self._get_data_model_cls()
        if model_cls is not None:
            merged_types = self._collect_type_array()
            pure = self._cast_to_pure(model_cls)
            data = pure.to_json(**kwargs)
            if merged_types:
                data["type"] = merged_types
            return data
        return super().to_json(**kwargs)

    def to_jsonld(self):
        model_cls = self._get_data_model_cls()
        if model_cls is not None:
            merged_types = self._collect_type_array()
            pure = self._cast_to_pure(model_cls)
            data = pure.to_jsonld()
            if merged_types:
                data["type"] = merged_types
            return data
        return super().to_jsonld()
