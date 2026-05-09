"""Tests for BaseController serialization and model detection."""

from typing import List, Optional

from pydantic import ConfigDict, Field

from oold.model import BaseController, LinkedBaseModel

# -- Test models --


class ModelA(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "ModelA"})
    type: Optional[List[str]] = ["Category:OSWModelA"]
    field_a: str = "default_a"


class ModelB(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "ModelB"})
    type: Optional[List[str]] = ["Category:OSWModelB"]
    field_b: str = "default_b"


# -- Single model base --


class SingleController(BaseController, ModelA):
    controller_field: str = "ctrl_value"


def test_auto_detect_single_base():
    ctrl = SingleController(name="test", label=[])
    model_cls = ctrl._get_data_model_cls()
    assert model_cls is ModelA


def test_to_json_strips_controller_fields():
    ctrl = SingleController(name="test", label=[])
    j = ctrl.to_json()
    assert "field_a" in j
    assert "controller_field" not in j


def test_to_json_preserves_type():
    ctrl = SingleController(name="test", label=[])
    j = ctrl.to_json()
    assert j["type"] == ["Category:OSWModelA"]


def test_round_trip_single():
    ctrl = SingleController(name="test", label=[])
    j = ctrl.to_json()
    restored = ModelA.from_json(j)
    assert restored.field_a == "default_a"


# -- Multiple model bases --


class MultiController(BaseController, ModelA, ModelB):
    multi_ctrl_field: str = "multi_ctrl"


def test_auto_detect_multi_base():
    ctrl = MultiController(name="test", label=[])
    model_cls = ctrl._get_data_model_cls()
    assert model_cls is not None
    assert hasattr(model_cls, "_union_bases")
    assert ModelA in model_cls._union_bases
    assert ModelB in model_cls._union_bases


def test_multi_to_json_strips_controller_fields():
    ctrl = MultiController(name="test", label=[])
    j = ctrl.to_json()
    assert "field_a" in j
    assert "multi_ctrl_field" not in j


def test_multi_to_json_merges_type_arrays():
    ctrl = MultiController(name="test", label=[])
    j = ctrl.to_json()
    assert "Category:OSWModelA" in j["type"]
    assert "Category:OSWModelB" in j["type"]
    assert len(j["type"]) == 2


def test_multi_get_model_bases():
    ctrl = MultiController(name="test", label=[])
    bases = ctrl._get_model_bases()
    assert len(bases) == 2
    assert ModelA in bases
    assert ModelB in bases


# -- Edge: no model base --


def test_base_controller_is_plain_class():
    """BaseController is not a LinkedBaseModel subclass."""
    assert not issubclass(BaseController, LinkedBaseModel)


# -- Range field preservation --


class Parent(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={"title": "Parent"},
    )
    type: Optional[List[str]] = ["Category:OSWParent"]
    children: Optional[List["Child"]] = None
    ref: Optional[str] = Field(None, json_schema_extra={"range": "Category:Target"})


class Child(LinkedBaseModel):
    model_config = ConfigDict(
        json_schema_extra={"title": "Child"},
    )
    value: int = 0
    ref: Optional[str] = Field(
        None, json_schema_extra={"range": "Category:ChildTarget"}
    )


class ParentController(BaseController, Parent):
    ctrl_field: str = "ctrl"


def test_to_json_preserves_range_iris():
    """to_json() preserves IRI references on range fields."""
    ctrl = ParentController(
        name="test",
        label=[],
        ref="ex:target1",
        children=[Child(value=1, ref="ex:child_target")],
    )
    j = ctrl.to_json()
    assert j["ref"] == "ex:target1"
    assert "ctrl_field" not in j


def test_to_json_preserves_nested_range_iris():
    """to_json() preserves IRI references on nested object range fields."""
    ctrl = ParentController(
        name="test",
        label=[],
        children=[Child(value=1, ref="ex:child_target")],
    )
    j = ctrl.to_json()
    assert "children" in j
    assert len(j["children"]) == 1
    assert j["children"][0]["ref"] == "ex:child_target"


def test_controller_round_trip():
    """Controller -> to_json -> from_json preserves all data."""
    ctrl = ParentController(
        name="test",
        label=[],
        ref="ex:target1",
        children=[Child(value=42, ref="ex:child_ref")],
    )
    j = ctrl.to_json()
    restored = Parent.from_json(j)
    assert restored.__iris__.get("ref") == "ex:target1"
    ch = restored.__dict__["children"][0]
    assert ch.__iris__.get("ref") == "ex:child_ref"
    assert ch.value == 42


def test_controller_from_model_preserves_iris():
    """ParentController(parent_model) preserves nested IRIs."""
    parent = Parent(
        name="src",
        label=[],
        ref="ex:parent_ref",
        children=[Child(value=7, ref="ex:nested_ref")],
    )
    ctrl = ParentController(parent, ctrl_field="custom")
    assert ctrl.__iris__.get("ref") == "ex:parent_ref"
    ch = ctrl.__dict__["children"][0]
    assert ch.__iris__.get("ref") == "ex:nested_ref"
    assert ctrl.ctrl_field == "custom"


# -- Controller auto-resolution --


def test_controller_registered_in_controller_types():
    """Controller classes are registered in _controller_types."""
    from oold.model import _controller_types

    iri = "Category:OSWParent"
    ctrls = _controller_types.get(iri, [])
    assert ParentController in ctrls


def test_resolve_type_prefers_controller():
    """resolve_type returns controller when exactly one is registered."""
    from oold.model import _types
    from oold.static import resolve_type

    cls = resolve_type("Category:OSWParent", _types)
    assert cls is ParentController


def test_resolve_type_falls_back_to_model():
    """resolve_type returns pure model when prefer_controller=False."""
    from oold.model import _types
    from oold.static import resolve_type

    cls = resolve_type("Category:OSWParent", _types, prefer_controller=False)
    assert cls is Parent


def test_from_json_returns_controller():
    """from_json auto-resolves to controller class."""
    parent = Parent(
        name="test",
        label=[],
        ref="ex:ref1",
    )
    j = parent.to_json()
    restored = LinkedBaseModel.from_json(j)
    assert type(restored).__name__ == "ParentController"
    assert hasattr(restored, "ctrl_field")


def test_from_json_controller_failure_falls_back():
    """If controller construction fails, fall back to pure model."""

    class StrictController(BaseController, ModelA):
        mandatory: str  # no default - construction from JSON will fail

    j = ModelA(name="test", label=[]).to_json()
    # Should fall back to ModelA with a warning
    restored = LinkedBaseModel.from_json(j)
    # StrictController failed, so we get ModelA or another controller
    assert hasattr(restored, "field_a")
