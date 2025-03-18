import json
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

from pydantic.v1 import BaseModel, PrivateAttr

from oold.model.static import GenericLinkedBaseModel

if TYPE_CHECKING:
    from pydantic.v1.typing import AbstractSetIntStr, MappingIntStrAny


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

    __iris__: Optional[Dict[str, Union[str, List[str]]]] = PrivateAttr()

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
                exclude_none=exclude_none,
                encoder=encoder,
                models_as_dict=models_as_dict,
                **dumps_kwargs,
            )
        )  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **dumps_kwargs)


# required for pydantic v1
SetResolverParam.update_forward_refs()
GetResolverResult.update_forward_refs()
ResolveResult.update_forward_refs()
