"""Tests for BaseController serialization and model detection."""

from typing import List, Optional

from pydantic import ConfigDict

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
