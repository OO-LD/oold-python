"""Tests for `oold` package."""

import json
from pathlib import Path
from typing import Any

import datamodel_code_generator

from oold.backend.interface import (
    ResolveParam,
    Resolver,
    ResolveResult,
    SetResolverParam,
    set_resolver,
)
from oold.generator import Generator


def _run(pydantic_version="v1"):
    if pydantic_version == "v1":
        output_model_type = datamodel_code_generator.DataModelType.PydanticBaseModel
    else:
        output_model_type = datamodel_code_generator.DataModelType.PydanticV2BaseModel

    """Tests for `oold` package."""

    schemas = [
        {
            "@context": {
                "id": "@id",
                "type": "@type",
                "ex": "http://example.com/",
                "@base": "http://example.com/",
                "prop1": "ex:prop1",
            },  # noqa: E501
            "uuid": "bar2/Bar2.json",
            "id": "./bar2/Bar2",
            "title": "Bar2",
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "type": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Bar2"],
                },
                "prop1": {"type": "string"},
                "unit": {
                    # "units": {"type": "array", "items": {
                    "title": "LengthUnit",
                    "type": "string",
                    "enum": [
                        "Item:OSWf101d25e944856e3bd4b4c9863db7de2",
                        "Item:OSWf101d25e944856e3bd4b4c9863db7de2#OSW322dec469be75aedb008b3ebff29db86",  # noqa: E501
                        "Item:OSWf101d25e944856e3bd4b4c9863db7de2#OSWb1de8f91f1275572b37c2edfe40d5de6",  # noqa: E501
                    ],
                    "defaut": "Item:OSWf101d25e944856e3bd4b4c9863db7de2",
                    "$comment": "enum_titles are valid variable names and follow latex SI unit notation with '\\' replaced with '_'",  # noqa: E501
                    "x-enum-varnames": ["meter", "milli_meter", "kilo_meter"],
                    "enum_titles*": {
                        "$comment": "Human friedly symbols",
                        "en": ["m", "mm", "km"],
                    }
                    # }
                },
            },
        },
        {
            "@context": ["./bar2/Bar2.json"],
            "id": "Bar",
            "title": "Bar",
            "type": "object",
            "allOf": [{"$ref": "./bar2/Bar2.json"}],
            "properties": {
                "type": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Bar"],
                },
                "prop2": {"type": "string"},
                "unit": {
                    "_allOf": [{"$ref": "./bar2/Bar2.json#/properties/unit"}],
                    "title": "DiameterUnit",
                },
            },
        },
        {
            "id": "Foo",
            "title": "Foo",
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "type": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Foo"],
                },
                "literal": {"type": "string"},
                "b": {"type": "string", "range": "Bar.json"},
                "b2": {
                    "type": "array",
                    "items": {"type": "string", "range": "Bar.json"},
                },
            },
        },
    ]
    graph = [
        {
            "id": "ex:f",
            "type": ["Foo"],
            "literal": "test1",
            "b": "ex:b",
            "b2": ["ex:b1", "ex:b2"],
        },
        {"id": "ex:b", "type": ["Bar"], "prop1": "test2"},
        {"id": "ex:b1", "type": ["Bar"], "prop1": "test3"},
        {"id": "ex:b2", "type": ["Bar"], "prop1": "test4"},
    ]

    g = Generator()
    g.generate(
        Generator.GenerateParams(
            json_schemas=schemas,
            main_schema="Foo.json",
            output_model_type=output_model_type,
            output_model_path=Path(__file__).parent
            / "data"
            / "quantities"
            / ("model.py"),
        )
    )
    import data.quantities.model as model

    # print(model.Bar2.model_json_schema())

    b = model.Bar(id="ex:b", prop1="test2")
    print(b.json())
    return

    class MyResolver(Resolver):
        graph: (Any)

        def resolve_iri(self, iri):
            for node in self.graph:
                if node["id"] == iri:
                    cls = node["type"][0]
                    entity = eval(f"model.{cls}(**node)")
                    return entity

        def resolve(self, request: ResolveParam):
            # print("RESOLVE", request)
            nodes = {}
            for iri in request.iris:
                nodes[iri] = self.resolve_iri(iri)
            return ResolveResult(nodes=nodes)

    r = MyResolver(graph=graph)
    set_resolver(SetResolverParam(iri="ex", resolver=r))

    f = model.Foo(id="ex:f", literal="test1", b="ex:b", b2=["ex:b1", "ex:b2"])
    print(f.b)

    print(f.b.id)
    assert f.b.id == "ex:b"
    for b in f.b2:
        print(b)
    assert f.b2[0].id == "ex:b1" and f.b2[0].prop1 == "test3"
    assert f.b2[1].id == "ex:b2" and f.b2[1].prop1 == "test4"

    f = model.Foo(
        id="ex:f",
        literal="test1",
        b=model.Bar(id="ex:b", prop1="test2"),
        b2=[model.Bar(id="ex:b1", prop1="test3"), model.Bar(id="ex:b2", prop1="test4")],
    )
    assert f.b.id == "ex:b"
    for b in f.b2:
        print(b)
    assert f.b2[0].id == "ex:b1" and f.b2[0].prop1 == "test3"
    assert f.b2[1].id == "ex:b2" and f.b2[1].prop1 == "test4"

    def export_json(obj):
        if pydantic_version == "v1":
            return obj.json(exclude_none=True)
        return obj.model_dump_json(exclude_none=True)

    print(export_json(f.b))
    assert json.loads(export_json(f)) == graph[0]
    assert json.loads(export_json(f.b)) == graph[1]
    assert json.loads(export_json(f.b2[0])) == graph[2]
    assert json.loads(export_json(f.b2[1])) == graph[3]


def test_core():
    _run(pydantic_version="v1")
    _run(pydantic_version="v2")
    pass


if __name__ == "__main__":
    test_core()
