"""Tests for `oold` package."""

import json
from pathlib import Path
from typing import Any

import datamodel_code_generator

from oold.generator import Generator


def _run(pydantic_version="v1"):
    if pydantic_version == "v1":
        from oold.model.v1 import (
            ResolveParam,
            Resolver,
            ResolveResult,
            SetResolverParam,
            set_resolver,
        )

        output_model_type = datamodel_code_generator.DataModelType.PydanticBaseModel
    else:
        from oold.model import (
            ResolveParam,
            Resolver,
            ResolveResult,
            SetResolverParam,
            set_resolver,
        )

        output_model_type = datamodel_code_generator.DataModelType.PydanticV2BaseModel

    """Tests for `oold` package."""

    schemas = [
        {
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
            },
        },
        {
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
            },
        },
        {
            "id": "Foo",
            "title": "Foo",
            "type": "object",
            "required": ["id", "b"],
            "properties": {
                "id": {"type": "string"},
                "type": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Foo"],
                },
                "literal": {"type": "string"},
                "b": {"type": "string", "range": "Bar.json"},
                "b_default": {"type": "string", "range": "Bar.json", "default": "ex:b"},
                "b_set_later": {"type": "string", "range": "Bar.json"},
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
            # will be automatically added by the class constructor
            # "b_default": "ex:b",
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
            / "test_core"
            / ("model_" + pydantic_version + ".py"),
            working_dir_path=Path(__file__).parent / "data" / "test_core" / "src",
        )
    )

    if pydantic_version == "v1":
        from data.test_core import model_v1 as model
    else:
        from data.test_core import model_v2 as model

    class MyResolver(Resolver):
        graph: (Any)

        def resolve_iri(self, iri):
            for node in self.graph:
                if node["id"] == iri:
                    cls_name = node["type"][0]
                    cls = getattr(model, cls_name)
                    entity = cls(**node)
                    return entity

        def resolve(self, request: ResolveParam):
            # print("RESOLVE", request)
            nodes = {}
            for iri in request.iris:
                nodes[iri] = self.resolve_iri(iri)
            return ResolveResult(nodes=nodes)

    r = MyResolver(graph=graph)
    set_resolver(SetResolverParam(iri="ex", resolver=r))

    # Test if the model can be created with string IRIs
    f = model.Foo(id="ex:f", literal="test1", b="ex:b", b2=["ex:b1", "ex:b2"])
    f.b_set_later = "ex:b"

    assert f.b.id == "ex:b"
    assert f.b_set_later.id == "ex:b"
    for b in f.b2:
        assert b.id.startswith("ex:b")
    assert f.b2[0].id == "ex:b1" and f.b2[0].prop1 == "test3"
    assert f.b2[1].id == "ex:b2" and f.b2[1].prop1 == "test4"
    assert f.b_default.id == "ex:b"

    # Test if the model can be created with objects
    f = model.Foo(
        id="ex:f",
        literal="test1",
        b=model.Bar(id="ex:b", prop1="test2"),
        b2=[model.Bar(id="ex:b1", prop1="test3"), model.Bar(id="ex:b2", prop1="test4")],
    )
    f.b_set_later = model.Bar(id="ex:b", prop1="test2")
    assert f.b.id == "ex:b"
    assert f.b_set_later.id == "ex:b"
    for b in f.b2:
        assert b.id.startswith("ex:b")
    assert f.b2[0].id == "ex:b1" and f.b2[0].prop1 == "test3"
    assert f.b2[1].id == "ex:b2" and f.b2[1].prop1 == "test4"

    def export_json(obj):
        if pydantic_version == "v1":
            return obj.json(exclude_none=True)
        return obj.model_dump_json(exclude_none=True)

    assert json.loads(export_json(f)) == {
        **graph[0],
        **{"b_default": "ex:b", "b_set_later": "ex:b"},
    }
    assert json.loads(export_json(f.b)) == graph[1]
    assert json.loads(export_json(f.b2[0])) == graph[2]
    assert json.loads(export_json(f.b2[1])) == graph[3]

    # unset property should be None
    f.b_set_later = None
    assert f.b_set_later is None
    f_json = json.loads(export_json(f))
    assert "b_set_later" not in f_json

    # Test nonexisting IRIs => properties should be initialized to None
    # but IRI is persisted when exporting to JSON
    f = model.Foo(
        id="ex:f",
        literal="test1",
        b="ex:b",
        b_default="ex:doesNotExist",
        b2=["ex:b1", "ex:doesNotExist"],
    )

    assert f.b_default is None
    assert f.b2[1] is None
    f_json = json.loads(export_json(f))
    assert f_json["b_default"] == "ex:doesNotExist"
    assert f_json["b2"][1] == "ex:doesNotExist"

    # test if skipping of a required property throws an exception
    # assert that ValueError is raised, fail if non is raised
    try:
        f = model.Foo(
            id="ex:f",
            literal="test1",
            # b="ex:b",
            b_default="ex:doesNotExist",
            b2=["ex:b1", "ex:doesNotExist"],
        )
    except Exception as e:
        assert isinstance(e, ValueError)
    else:
        assert False, "ValueError not raised"


def test_core():
    _run(pydantic_version="v1")
    _run(pydantic_version="v2")


if __name__ == "__main__":
    test_core()
