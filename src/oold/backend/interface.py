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
    def resolve_iri(self, iri) -> Dict:
        pass

    def resolve(self, request: ResolveParam):
        # print("RESOLVE", request)

        model_cls = request.model_cls
        if model_cls is None:
            model_cls = self.model_cls
        if model_cls is None:
            raise ValueError("No model_cls provided in request or resolver")

        nodes = {}
        for iri in request.iris:
            # nodes[iri] = self.resolve_iri(iri)
            jsonld_dict = self.resolve_iri(iri)
            nodes[iri] = model_cls.from_jsonld(jsonld_dict)
        return ResolveResult(nodes=nodes)


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
