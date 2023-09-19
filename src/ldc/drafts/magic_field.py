import json
from pprint import pprint
from typing import Dict, Optional, Union

from pydantic import BaseModel, Field


class LinkedBaseModel(BaseModel):
    type: str
    id: str
    _iris: Optional[Dict[str, str]] = {}

    def __init__(self, *a, **kw):
        # print("Init")
        # pprint(a)
        # pprint(kw)
        for name in list(kw):  # force copy of keys for inline-delete
            # rewrite <attr> to <attr>_iri
            # => if "range" in self.__fields__[name].field_info.extra
            # pprint(self.__fields__)
            if name + "_iri" in self.__fields__:  # pydantic v2: model_fields
                if isinstance(kw[name], BaseModel):  # contructed with object ref
                    kw[name + "_iri"] = kw[name].id
                elif isinstance(kw[name], str):  # constructed from json
                    kw[name + "_iri"] = kw[name]
                    del kw[name]
            # rewrite <attr>_iri to <attr>
            # stripped_name = name.replace("_iri", "")
            # if stripped_name != name and stripped_name in self.__fields__:
            #    kw[name + "_iri"] = kw[name]
            #    del kw[name]
        # pprint(kw)
        super().__init__(*a, **kw)

    def __getattribute__(self, name):
        # async? https://stackoverflow.com/questions/33128325/how-to-set-class-attribute-with-await-in-init
        # print("__getattribute__ ", name)
        if name == "__dict__":
            return BaseModel.__getattribute__(self, name)  # prevent loop
        # iri = BaseModel.__getattribute__(self, name + "_iri")
        # if hasattr(self, name + "_iri"):
        if name + "_iri" in self.__dict__:
            # print("in dict")
            iri = self.__dict__[name + "_iri"]
            # we will need an osw instance here
            # if iri in graph:
            # print("in graph")
            node = get(iri)
            if node:
                self.__setattr__(name, node)
        return BaseModel.__getattribute__(self, name)

    def _object_to_iri(self, d):
        for name in list(d):  # force copy of keys for inline-delete
            if hasattr(self, name + "_iri"):
                d[name] = getattr(self, name + "_iri")
                del d[name + "_iri"]
                # Include selected private properties. note: private properties are not
                #  considered as discriminator
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
    b_iri: str
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
