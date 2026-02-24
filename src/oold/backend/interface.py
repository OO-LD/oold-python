from abc import abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Type, Union

from pydantic import BaseModel

from oold.static import GenericLinkedBaseModel


class SetResolverParam(BaseModel):
    iri: str
    resolver: "Resolver"


class GetResolverParam(BaseModel):
    iri: str


class GetResolverResult(BaseModel):
    resolver: "Resolver"


class ResolveParam(BaseModel):
    iris: List[str]
    model_cls: Optional[Type[GenericLinkedBaseModel]] = None


class ResolveResult(BaseModel):
    model_config = {
        "arbitrary_types_allowed": True,
    }
    nodes: Dict[str, Union[None, GenericLinkedBaseModel]]


class Query(BaseModel):
    op1: Union["Query", "Condition"]
    operator: str
    op2: Union["Query", "Condition"]

    # override the & operator
    def __and__(self, other):
        return Query(op1=self, operator="and", op2=other)


class Condition(BaseModel):
    field: str
    operator: Optional[str] = None
    value: Optional[Union[str, int, float]] = None

    # override the == operator
    def __eq__(self, other):
        self.operator = "eq"
        self.value = other
        return self

    # override the & operator
    def __and__(self, other):
        return Query(op1=self, operator="and", op2=other)


class QueryParam(BaseModel):
    query: Union[Query, Condition]
    model_cls: Optional[Type[GenericLinkedBaseModel]] = None


class LinkedDataFormat(str, Enum):
    JSON_LD = "JSON-LD"
    JSON = "JSON"


class Resolver(BaseModel):
    model_cls: Optional[Type[GenericLinkedBaseModel]] = None
    format: Optional[LinkedDataFormat] = LinkedDataFormat.JSON_LD

    @abstractmethod
    def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
        pass

    def resolve(self, request: ResolveParam):
        # print("RESOLVE", request)

        model_cls = request.model_cls
        if model_cls is None:
            model_cls = self.model_cls
        if model_cls is None:
            raise ValueError("No model_cls provided in request or resolver")

        jsonld_dicts = self.resolve_iris(request.iris)
        nodes = {}
        for iri, jsonld_dict in jsonld_dicts.items():
            if jsonld_dict is None:
                nodes[iri] = None
            else:
                if self.format == LinkedDataFormat.JSON_LD:
                    node = model_cls.from_jsonld(jsonld_dict)
                elif self.format == LinkedDataFormat.JSON:
                    node = model_cls.from_json(jsonld_dict)
                else:
                    raise ValueError(f"Unsupported format {self.format}")
                nodes[iri] = node

        return ResolveResult(nodes=nodes)

    def query(self, param: QueryParam) -> ResolveResult:
        """Query the backend and return a ResolveResult."""
        raise NotImplementedError("Query method not implemented in Resolver subclass")


global _resolvers
_resolvers = {}


def set_resolver(param: SetResolverParam) -> None:
    _resolvers[param.iri] = param.resolver


def get_resolver(param: GetResolverParam) -> GetResolverResult:
    # ToDo: Handle prefixes (ex:) as well as full IRIs (http://example.com/)
    # ToDo: Handle list of IRIs with mixed domains
    iri = param.iri.split(":")[0]
    if iri not in _resolvers:
        raise ValueError(f"No resolvers found for {iri}")
    return GetResolverResult(resolver=_resolvers[iri])


class SetBackendParam(BaseModel):
    iri: str
    backend: "Backend"


class GetBackendParam(BaseModel):
    iri: str


class GetBackendResult(BaseModel):
    backend: "Backend"


class StoreParam(BaseModel):
    model_config = {
        "arbitrary_types_allowed": True,
    }
    nodes: Dict[str, Union[None, GenericLinkedBaseModel]]


class StoreResult(BaseModel):
    success: bool


class Backend(Resolver):
    def store(self, param: StoreParam) -> StoreResult:
        jsonld_dicts = {}
        for iri, node in param.nodes.items():
            if node is None:
                jsonld_dicts[iri] = None
            else:
                if self.format == LinkedDataFormat.JSON_LD:
                    jsonld_dicts[iri] = node.to_jsonld()
                elif self.format == LinkedDataFormat.JSON:
                    jsonld_dicts[iri] = node.to_json()
                else:
                    raise ValueError(f"Unsupported format {self.format}")
        if self.format == LinkedDataFormat.JSON:
            return self.store_json_dicts(jsonld_dicts)
        else:
            return self.store_jsonld_dicts(jsonld_dicts)

    def store_jsonld_dicts(self, jsonld_dicts: Dict[str, Dict]) -> StoreResult:
        raise NotImplementedError(
            "store_jsonld_dicts method not implemented in Backend subclass"
        )

    def store_json_dicts(self, json_dicts: Dict[str, Dict]) -> StoreResult:
        raise NotImplementedError(
            "store_json_dicts method not implemented in Backend subclass"
        )


global _backends
_backends = {}


def set_backend(param: SetBackendParam) -> None:
    _resolvers[param.iri] = param.backend
    _backends[param.iri] = param.backend


def get_backend(param: GetBackendParam) -> GetBackendResult:
    iri = param.iri.split(":")[0]
    if iri not in _backends:
        raise ValueError(f"No backends found for {iri}")
    return GetBackendResult(backend=_backends[iri])
