"""Tests for the public controller-registry API.

Controllers register themselves in ``_controller_types`` on creation, but no
public entry point existed to read that mapping, so a caller holding an entity
could not find the controller that implements it without knowing the concrete
class. These functions are that entry point.
"""

import pytest
from pydantic import ConfigDict

from oold.model import (
    BaseController,
    LinkedBaseModel,
    _controller_types,
    _types,
    find_controller_type,
    get_registered_controller_types,
    register_controller_type,
    registered_controller_types,
)


class CtrlModel(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "CtrlModel"})
    type: list[str] | None = ["Category:OSWCtrlModel"]
    field_a: str = "default_a"


class ExampleController(BaseController, CtrlModel):
    controller_field: str = "ctrl_value"


def test_controllers_register_themselves_on_creation():
    assert ExampleController in get_registered_controller_types("Category:OSWCtrlModel")


def test_controllers_do_not_shadow_the_data_model():
    """The type registry must still resolve the IRI to the model."""
    assert _types["Category:OSWCtrlModel"] is CtrlModel


def test_register_controller_type_with_explicit_iri():
    dyn = type("CtrlDyn", (ExampleController,), {})
    register_controller_type(dyn, "Category:OSWCtrlAlias")
    assert get_registered_controller_types("Category:OSWCtrlAlias") == [dyn]


def test_register_controller_type_is_idempotent():
    register_controller_type(ExampleController)
    assert get_registered_controller_types("Category:OSWCtrlModel").count(ExampleController) == 1


def test_register_controller_type_accepts_a_list_of_iris():
    dyn = type("CtrlMulti", (ExampleController,), {})
    register_controller_type(dyn, ["Category:OSWCtrlA", "Category:OSWCtrlB"])
    assert get_registered_controller_types("Category:OSWCtrlA") == [dyn]
    assert get_registered_controller_types("Category:OSWCtrlB") == [dyn]


def test_registry_identity_is_shared():
    assert registered_controller_types() is _controller_types


def test_unknown_iri_returns_empty_list():
    assert get_registered_controller_types("Category:OSWNeverRegistered") == []


def test_class_without_iri_raises_clearly():
    with pytest.raises(ValueError, match="no type IRI"):
        register_controller_type(type("CtrlNoIri", (object,), {}))


class LookupModel(LinkedBaseModel):
    """Own IRI, so subclasses created elsewhere cannot register against it."""

    model_config = ConfigDict(json_schema_extra={"title": "LookupModel"})
    type: list[str] | None = ["Category:OSWLookupModel"]


class LookupController(BaseController, LookupModel):
    pass


def test_find_controller_type_tries_iris_in_order():
    found = find_controller_type(["Category:OSWUnknown", "Category:OSWLookupModel"])
    assert found is LookupController


def test_find_controller_type_accepts_a_single_iri():
    assert find_controller_type("Category:OSWLookupModel") is LookupController


def test_find_controller_type_filters_by_base():
    assert find_controller_type("Category:OSWLookupModel", base=BaseController) is LookupController

    class Unrelated:
        pass

    assert find_controller_type("Category:OSWLookupModel", base=Unrelated) is None


def test_find_controller_type_prefers_the_latest_registration():
    """A downstream package overrides an implementation by importing its own."""
    iri = "Category:OSWCtrlOverride"
    first = type("CtrlFirst", (ExampleController,), {})
    second = type("CtrlSecond", (ExampleController,), {})
    register_controller_type(first, iri)
    register_controller_type(second, iri)
    assert find_controller_type(iri) is second


def test_find_controller_type_returns_none_for_unknown_iri():
    assert find_controller_type("Category:OSWNeverRegistered") is None
