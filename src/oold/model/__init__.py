import json
from abc import abstractmethod
from typing import Any, Dict, List, Literal, Optional, Union

import pydantic
from pydantic import BaseModel
from typing_extensions import Self  # to support python < 3.11

from oold.model.static import GenericLinkedBaseModel, export_jsonld, import_jsonld


class SetResolverParam(BaseModel):
    iri: str
    resolver: "Resolver"


class GetResolverParam(BaseModel):
    iri: str


class GetResolverResult(BaseModel):
    resolver: "Resolver"


class ResolveParam(BaseModel):
    iris: List[str]


class ResolveResult(BaseModel):
    nodes: Dict[str, Union[None, "LinkedBaseModel"]]


class Resolver(BaseModel):
    @abstractmethod
    def resolve(self, request: ResolveParam) -> ResolveResult:
        pass


global _resolvers
_resolvers = {}


def set_resolver(param: SetResolverParam) -> None:
    _resolvers[param.iri] = param.resolver


def get_resolver(param: GetResolverParam) -> GetResolverResult:
    # ToDo: Handle prefixes (ex:) as well as full IRIs (http://example.com/)
    iri = param.iri.split(":")[0]
    if iri not in _resolvers:
        raise ValueError(f"No resolvers found for {iri}")
    return GetResolverResult(resolver=_resolvers[iri])


# pydantic v2
_types: Dict[str, pydantic.main._model_construction.ModelMetaclass] = {}


# pydantic v2
class LinkedBaseModelMetaClass(pydantic.main._model_construction.ModelMetaclass):
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        schema = {}

        # pydantic v2
        if "model_config" in namespace:
            if "json_schema_extra" in namespace["model_config"]:
                schema = namespace["model_config"]["json_schema_extra"]

        if "iri" in schema:
            iri = schema["iri"]
            _types[iri] = cls
        return cls


class LinkedBaseModel(
    BaseModel, GenericLinkedBaseModel, metaclass=LinkedBaseModelMetaClass
):
    """LinkedBaseModel for pydantic v2"""

    __iris__: Optional[Dict[str, Union[str, List[str]]]] = {}

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
                            self.__setattr__(name, node_list)
                        else:
                            node = node_dict[iris[0]]
                            if node:
                                self.__setattr__(name, node)

        return BaseModel.__getattribute__(self, name)

    def model_dump(self, **kwargs):  # extent BaseClass export function
        # print("dict")
        remove_none = kwargs.get("remove_none", False)
        kwargs["exclude_none"] = False
        d = super().model_dump(**kwargs)
        # pprint(d)
        self._object_to_iri(d)
        if remove_none:
            d = self.remove_none(d)
        # pprint(d)
        return d

    @staticmethod
    def _resolve(iris):
        resolver = get_resolver(GetResolverParam(iri=iris[0])).resolver
        node_dict = resolver.resolve(ResolveParam(iris=iris)).nodes
        return node_dict

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
        if exclude_none:
            d = self.remove_none(d)
        return json.dumps(d, **dumps_kwargs)

    def to_jsonld(self) -> Dict:
        """Return the RDF representation of the object as JSON-LD."""
        return export_jsonld(self, BaseModel)

    @classmethod
    def from_jsonld(self, jsonld: Dict) -> "LinkedBaseModel":
        """Constructs a model instance from a JSON-LD representation."""
        return import_jsonld(BaseModel, jsonld, _types)
