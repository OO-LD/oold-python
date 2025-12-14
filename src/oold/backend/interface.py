from abc import abstractmethod
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


class Resolver(BaseModel):
    model_cls: Optional[Type[GenericLinkedBaseModel]] = None

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
                node = model_cls.from_jsonld(jsonld_dict)
                nodes[iri] = node

        return ResolveResult(nodes=nodes)


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


class Query(BaseModel):
    pass


class Backend(Resolver):
    def store(self, param: StoreParam) -> StoreResult:
        jsonld_dicts = {}
        for iri, node in param.nodes.items():
            if node is None:
                jsonld_dicts[iri] = None
            else:
                jsonld_dicts[iri] = node.to_jsonld()
        return self.store_jsonld_dicts(jsonld_dicts)

    @abstractmethod
    def store_jsonld_dicts(self, jsonld_dicts: Dict[str, Dict]) -> StoreResult:
        pass

    @abstractmethod
    def query(self, query: Query) -> ResolveResult:
        """Query the backend and return a ResolveResult."""
        pass


global _backends
_backends = {}


def set_backend(param: SetBackendParam) -> None:
    _backends[param.iri] = param.backend


def get_backend(param: GetBackendParam) -> GetBackendResult:
    iri = param.iri.split(":")[0]
    if iri not in _backends:
        raise ValueError(f"No backends found for {iri}")
    return GetBackendResult(backend=_backends[iri])
