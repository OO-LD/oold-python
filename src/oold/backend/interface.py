from abc import abstractmethod
from typing import Dict, List, Union

from pydantic import BaseModel

from oold.model.static import GenericLinkedBaseModel


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
    model_config = {
        "arbitrary_types_allowed": True,
    }
    nodes: Dict[str, Union[None, GenericLinkedBaseModel]]


class Resolver(BaseModel):
    @abstractmethod
    def resolve(self, request: ResolveParam) -> ResolveResult:
        pass
