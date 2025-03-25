import json
from abc import abstractmethod
from typing import Any, Dict, List, Literal, Optional, Union

import pydantic
from pydantic import BaseModel

from oold.model.static import GenericLinkedBaseModel, export_jsonld


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


class LinkedBaseModel(BaseModel, GenericLinkedBaseModel):
    """LinkedBaseModel for pydantic v1"""

    __iris__: Optional[Dict[str, Union[str, List[str]]]] = {}

    def get_iri(self) -> str:
        """Return the unique IRI of the object.
        Overwrite this method in the subclass."""
        return self.id

    def __init__(self, *a, **kw):
        if "__iris__" not in kw:
            kw["__iris__"] = {}

        for name in list(kw):  # force copy of keys for inline-delete
            if name == "__iris__":
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
                        del kw[name]
                else:
                    if isinstance(kw[name], BaseModel):  # contructed with object ref
                        # print(kw[name].id)
                        kw["__iris__"][name] = kw[name].get_iri()
                    elif isinstance(kw[name], str):  # constructed from json
                        kw["__iris__"][name] = kw[name]
                        # pydantic v1
                        # kw[name] = None # else pydantic v1 will set a FieldInfo object
                        # pydantic v2
                        del kw[name]

        BaseModel.__init__(self, *a, **kw)

        self.__iris__ = kw["__iris__"]

    def __getattribute__(self, name):
        # print("__getattribute__ ", name)
        # async? https://stackoverflow.com/questions/33128325/
        # how-to-set-class-attribute-with-await-in-init

        if name in ["__dict__", "__pydantic_private__", "__iris__"]:
            return BaseModel.__getattribute__(self, name)  # prevent loop

        else:
            if hasattr(self, "__iris__"):
                if name in self.__iris__:
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

    def _object_to_iri(self, d):
        for name in list(d.keys()):  # force copy of keys for inline-delete
            if name in self.__iris__:
                d[name] = self.__iris__[name]
                # del d[name + "_iri"]
        return d

    def dict(self, **kwargs):  # extent BaseClass export function
        # print("dict")
        d = super().dict(**kwargs)
        # pprint(d)
        self._object_to_iri(d)
        # pprint(d)
        return d

    def _resolve(self, iris):
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
                exclude_none=exclude_none,
                round_trip=round_trip,
                warnings=warnings,
                serialize_as_any=serialize_as_any,
            )
        )  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **dumps_kwargs)

    def to_jsonld(self) -> Dict:
        """Return the RDF representation of the object as JSON-LD."""
        return export_jsonld(self, BaseModel)
