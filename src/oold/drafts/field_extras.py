import json
from pprint import pprint
from typing import Dict, Optional, Union

from pydantic import BaseModel, Field


class LinkedBaseModel(BaseModel):
    type: str
    id: str
    __iris__: Optional[Dict[str, str]] = {}

    def __init__(self, *a, **kw):
        # pprint(a)
        # pprint(kw)
        for name in list(kw):  # force copy of keys for inline-delete
            # rewrite <attr> to <attr>_iri
            # pprint(self.__fields__)
            # if hasattr(self.__fields__[name], "extra") and "range" in self.__fields__[name].extra: # pydantic v1
            if not "__iris__" in kw:
                kw["__iris__"] = {}
            if (
                self.model_fields[name].json_schema_extra
                and "range" in self.model_fields[name].json_schema_extra
            ):  # pydantic v2: model_fields
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
        # async? https://stackoverflow.com/questions/33128325/how-to-set-class-attribute-with-await-in-init
        if name in ["__dict__", "__pydantic_private__", "__iris__"]:
            return BaseModel.__getattribute__(self, name)  # prevent loop
        # if name in ["__pydantic_extra__"]
        if "__iris__" in self.__dict__:
            if name in self.__dict__["__iris__"]:
                # if self.__iris__:
                #    if name in self.__iris__:
                # print("in dict")
                iri = self.__iris__[name]
                # we will need an osw instance here
                # if iri in graph:
                # print("in graph")
                node = get(iri)
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
        # print("json")
        d = json.loads(BaseModel.json(self, **kwargs))  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **kwargs)

    def model_dump_json(self, **kwargs):
        # print("json")
        d = json.loads(
            BaseModel.model_dump_json(self, **kwargs)
        )  # ToDo directly use dict?
        self._object_to_iri(d)
        return json.dumps(d, **kwargs)


class Bar(LinkedBaseModel):
    type: Optional[str] = "Bar"
    prop1: str


class Foo(LinkedBaseModel):
    type: Optional[str] = "Foo"
    literal: str
    b: Optional[Bar] = Field(None, range="ex:test")


graph = [
    {
        "id": "ex:LinkedBaseModel",
        "type": "class",
        "properties": {"type": {"type": "string"}},
    },
    {
        "id": "ex:Bar",
        "type": "class",
        "properties": {"type": {"default": "Bar"}, "prop1": {"type": "string"}},
    },
    {
        "id": "ex:Foo",
        "type": "class",
        "properties": {
            "type": {"default": "Foo"},
            "literal": {"type": "string"},
            "b": {"type": "string", "format": "iri", "range": "ex:Bar"},
        },
    },
    {"id": "ex:a", "type": "Foo", "literal": "test1", "b": "ex:b"},
    {"id": "ex:b", "type": "Bar", "prop1": "test2"},
]


def get(iri) -> Union[None, LinkedBaseModel]:
    for node in graph:
        if node["id"] == iri:
            cls = node["type"]
            entity = eval(f"{cls}(**node)")
            return entity
    return None


b = Bar(id="ex:b1", prop1="test")
f2 = Foo(id="ex:f2", literal="test1", b=b)
f = get("ex:a")
pprint(f)
# print(f.b_iri)
pprint(f.b)
# pydantic 1
# pprint(f.json())
# pprint(f2.json())
# pydantic 2
pprint(f.model_dump_json())
pprint(f2.model_dump_json())
