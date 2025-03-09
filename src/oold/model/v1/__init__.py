import json
from abc import abstractmethod
from typing import Any, ClassVar, Dict, List, Optional, Union

from oold.model.static import GenericLinkedBaseModel
from pydantic.v1 import PrivateAttr
from pydantic.v1 import BaseModel

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

class LinkedBaseModel(BaseModel, GenericLinkedBaseModel[BaseModel]):
    id: str
    __pydantic_model__: ClassVar[Any] = BaseModel
    __iris__: Optional[Dict[str, Union[str, List[str]]]] = PrivateAttr()
    
    def _get_pydantic_basemodel(self):
        return BaseModel
    
    def _resolve(self, iris):
        resolver = get_resolver(GetResolverParam(iri=iris[0])).resolver
        node_dict = resolver.resolve(ResolveParam(iris=iris)).nodes
        return node_dict
    
    # pydantic v1
    def json(self, **kwargs):
        print("json")
        d = json.loads(BaseModel.json(self, **kwargs))  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **kwargs)


# required for pydantic v1
SetResolverParam.update_forward_refs()
GetResolverResult.update_forward_refs()
ResolveResult.update_forward_refs()