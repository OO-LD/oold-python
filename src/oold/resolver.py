import json
from abc import abstractmethod
from ast import TypeVar
from pprint import pprint
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel

import oold.model.example as example
from oold.static import AbstractStore

# generic resolver the uses typevar which could be LinkedBasedModel v1 or v2
TypeVarT = TypeVar("TypeVarT")


class DocumentDict(AbstractStore):
    graph: (Any)

    def store(self, request: AbstractStore.StoreRequest) -> AbstractStore.StoreResponse:
        pass

    def resolve_iri(self, iri):
        for node in self.graph:
            if node["iri"] == iri:
                cls = node["type"][0]
                entity = eval(f"model.{cls}(**node, resolver=self)")
                return entity

    def resolve(
        self, request: AbstractStore.ResolveRequest
    ) -> AbstractStore.ResolveResponse:
        print("RESOLVE", request)
        nodes = {}
        for iri in request.iris:
            nodes[iri] = self.resolve_iri(iri)
        return AbstractStore.ResolveResponse(nodes=nodes)
