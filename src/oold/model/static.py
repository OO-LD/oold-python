import json
from abc import abstractmethod
from pprint import pprint
from typing import Dict, List, Optional, Union

from pydantic import BaseModel


class ResolveRequest(BaseModel):
    iris: List[str]


class ResolveResponse(BaseModel):
    nodes: Dict[str, Union[None, "LinkedBaseModel"]]


class Resolver(BaseModel):
    @abstractmethod
    def resolve(self, request: ResolveRequest) -> ResolveResponse:
        pass


class LinkedBaseModel(BaseModel):
    resolver: Resolver
    type: str
    id: str
    __iris__: Optional[Dict[str, Union[str, List[str]]]] = {}

    def __init__(self, *a, **kw):
        # pprint(a)
        # pprint(kw)
        for name in list(kw):  # force copy of keys for inline-delete
            # rewrite <attr> to <attr>_iri
            # pprint(self.__fields__)
            # if hasattr(self.__fields__[name], "extra")
            # and "range" in self.__fields__[name].extra: # pydantic v1
            if "__iris__" not in kw:
                kw["__iris__"] = {}
            if (
                self.model_fields[name].json_schema_extra
                and "range" in self.model_fields[name].json_schema_extra
            ):  # pydantic v2: model_fields
                arg_is_list = isinstance(kw[name], list)

                # annotation_is_list = False
                # args = self.model_fields[name].annotation.__args__
                # if hasattr(args[0], "_name"):
                #    is_list = args[0]._name == "List"
                if arg_is_list:
                    kw["__iris__"][name] = []
                    for e in kw[name][:]:  # interate over copy of list
                        if isinstance(e, BaseModel):  # contructed with object ref
                            kw["__iris__"][name].append(e.id)
                        elif isinstance(e, str):  # constructed from json
                            kw["__iris__"][name].append(e)
                            kw[name].remove(e)  # remove to construct valid instance
                else:
                    if isinstance(kw[name], BaseModel):  # contructed with object ref
                        # print(kw[name].id)
                        kw["__iris__"][name] = kw[name].id
                    elif isinstance(kw[name], str):  # constructed from json
                        kw["__iris__"][name] = kw[name]
                        del kw[name]
        pprint(kw)
        super().__init__(*a, **kw)
        self.__iris__ = kw["__iris__"]

    def __getattribute__(self, name):
        # print("__getattribute__ ", name)
        # async? https://stackoverflow.com/questions/33128325/
        # how-to-set-class-attribute-with-await-in-init
        if name in ["__dict__", "__pydantic_private__", "__iris__"]:
            return BaseModel.__getattribute__(self, name)  # prevent loop
        # if name in ["__pydantic_extra__"]
        if "__iris__" in self.__dict__:
            if name in self.__dict__["__iris__"]:
                if self.__dict__[name] is None or (
                    isinstance(self.__dict__[name], list)
                    and len(self.__dict__[name]) == 0
                ):
                    iris = self.__iris__[name]
                    is_list = isinstance(iris, list)
                    if not is_list:
                        iris = [iris]
                    node_dict = self.resolver.resolve(ResolveRequest(iris=iris)).nodes
                    if is_list:
                        node_list = []
                        for iri in iris:
                            node = node_dict[iris[0]]
                            node_list.append(node)
                        self.__setattr__(name, node_list)
                    else:
                        node = node_dict[iris[0]]
                        if node:
                            self.__setattr__(name, node)
        return BaseModel.__getattribute__(self, name)

    def _object_to_iri(self, d):
        for name in list(d):  # force copy of keys for inline-delete
            if name in self.__iris__:
                d[name] = self.__iris__[name]
                # del d[name + "_iri"]
        return d

    def dict(self, **kwargs):  # extent BaseClass export function
        print("dict")
        d = super().dict(**kwargs)
        # pprint(d)
        self._object_to_iri(d)
        # pprint(d)
        return d

    def json(self, **kwargs):
        print("json")
        d = json.loads(BaseModel.json(self, **kwargs))  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **kwargs)

    def model_dump_json(self, **kwargs):
        print("json")
        d = json.loads(
            BaseModel.model_dump_json(self, **kwargs)
        )  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **kwargs)
