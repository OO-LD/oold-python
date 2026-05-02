"""Tests for `oold` package."""

from pathlib import Path
from typing import Any, Dict, List

import datamodel_code_generator
import pytest

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

        def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
            jsonld_dicts = {}
            for iri in iris:
                jsonld_dicts[iri] = None
                for node in self.graph:
                    if node["id"] == iri:
                        jsonld_dicts[iri] = node
                        break
            return jsonld_dicts

        def resolve(self, request: ResolveParam):
            # print("RESOLVE", request)
            nodes = {}
            jsonld_dicts = self.resolve_iris(request.iris)
            for iri, jsonld_dict in jsonld_dicts.items():
                if jsonld_dict is None:
                    nodes[iri] = None
                    continue
                cls_name = jsonld_dict["type"][0]
                cls = getattr(model, cls_name)
                entity = cls(**jsonld_dict)
                nodes[iri] = entity
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

    assert f.to_json() == {
        **graph[0],
        **{"b_default": "ex:b", "b_set_later": "ex:b"},
    }
    assert f.b.to_json() == graph[1]
    assert f.b2[0].to_json() == graph[2]
    assert f.b2[1].to_json() == graph[3]

    # unset property should be None
    f.b_set_later = None
    assert f.b_set_later is None
    f_json = f.to_json()
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
    f_json = f.to_json()
    assert f_json["b_default"] == "ex:doesNotExist"
    assert f_json["b2"][1] == "ex:doesNotExist"

    # test importing from JSON
    f2 = model.Foo.from_json(
        {
            "id": "ex:f",
            "literal": "test1",
            "b": "ex:b",
            "b_default": "ex:doesNotExist",
            "b2": ["ex:b1", "ex:doesNotExist"],
        }
    )
    assert f2.b2[0].id == "ex:b1"

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

    # test index operator for getting objects by IRI
    f = model.Foo["ex:f"]
    assert f.id == "ex:f"
    [b1, b2] = model.Bar[["ex:b1", "ex:b2"]]
    assert b1.id == "ex:b1" and b2.id == "ex:b2"


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
@pytest.mark.benchmark(group="test_core")
def test_core(pydantic_version, benchmark):
    # benchmark.group += f"{pydantic_version = }"
    benchmark(_run, pydantic_version)


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_nested_iri_serialization(pydantic_version):
    """Test that IRIs in nested model objects are preserved during serialization."""
    if pydantic_version == "v1":
        from data.test_core.model_v1_nested import Container, NestedItem
    else:
        from data.test_core.model_v2_nested import Container, NestedItem

    c = Container(
        id="ex:c",
        items=[
            NestedItem(ref="ex:existing", value=1),
            NestedItem(ref="ex:doesNotExist", value=2),
        ],
    )
    c_json = c.to_json()
    assert "items" in c_json
    assert len(c_json["items"]) == 2
    assert c_json["items"][0]["ref"] == "ex:existing"
    assert c_json["items"][1]["ref"] == "ex:doesNotExist"
    assert c_json["items"][0]["value"] == 1
    assert c_json["items"][1]["value"] == 2

    # Test get_iri_ref helper
    item0 = c.__dict__["items"][0]
    assert item0.get_iri_ref("ref") == "ex:existing"
    item1 = c.__dict__["items"][1]
    assert item1.get_iri_ref("ref") == "ex:doesNotExist"
    assert item0.get_iri_ref("value") is None  # not an IRI field

    # Test get_raw helper
    assert item0.get_raw("ref") is None  # unresolved IRI → None internally
    assert item0.get_raw("value") == 1  # plain value preserved
    assert item0.get_raw("nonexistent") is None  # missing field


def _run_cast_tests(pydantic_version="v2"):
    if pydantic_version == "v1":
        from oold.model.v1 import LinkedBaseModel
    else:
        from oold.model import LinkedBaseModel

    class ModelA(LinkedBaseModel):
        value: float
        name: str = "default"

    class ModelB(LinkedBaseModel):
        value: float
        extra: str = "ext"

    class Narrow(LinkedBaseModel):
        value: float

    # cast to same class
    a = ModelA(value=42.0, name="hello")
    a2 = a.cast(ModelA)
    assert a2.value == 42.0
    assert a2.name == "hello"

    # cast to different class with kwargs
    b = ModelA(value=10.0).cast(ModelB, extra="custom")
    assert b.value == 10.0
    assert b.extra == "custom"

    # cast with remove_extra
    wide = ModelA(value=1.0, name="test")
    n = wide.cast(Narrow, remove_extra=True)
    assert n.value == 1.0

    # constructor from model instance: ModelB(model_a, extra="x")
    a3 = ModelA(value=5.0, name="src")
    b2 = ModelB(a3, extra="ctor")
    assert b2.value == 5.0
    assert b2.extra == "ctor"

    # constructor override: kwargs take precedence
    a4 = ModelA(value=5.0, name="src")
    a5 = ModelA(a4, name="overridden")
    assert a5.name == "overridden"
    assert a5.value == 5.0


def test_cast_v1():
    _run_cast_tests("v1")


def test_cast_v2():
    _run_cast_tests("v2")


if __name__ == "__main__":
    _run("v1")
    _run("v2")
