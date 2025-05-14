import json
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union

import pydantic
from pydantic.v1 import BaseModel, PrivateAttr

from oold.model.static import GenericLinkedBaseModel, export_jsonld, import_jsonld

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


# pydantic v1
_types: Dict[str, pydantic.v1.main.ModelMetaclass] = {}


# pydantic v1
class LinkedBaseModelMetaClass(pydantic.v1.main.ModelMetaclass):
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        schema = {}

        # pydantic v1
        if "Config" in namespace:
            if "schema_extra" in namespace["Config"].__dict__:
                schema = namespace["Config"].schema_extra

        if "iri" in schema:
            iri = schema["iri"]
            _types[iri] = cls
        return cls


class LinkedBaseModel(
    BaseModel, GenericLinkedBaseModel, metaclass=LinkedBaseModelMetaClass
):
    """LinkedBaseModel for pydantic v1"""

    __iris__: Optional[Dict[str, Union[str, List[str]]]] = PrivateAttr()

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

    def dict(self, **kwargs):  # extent BaseClass export function
        # print("dict")
        remove_none = kwargs.get("remove_none", False)
        kwargs["exclude_none"] = False
        d = super().dict(**kwargs)
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


# required for pydantic v1
SetResolverParam.update_forward_refs()
GetResolverResult.update_forward_refs()
ResolveResult.update_forward_refs()
