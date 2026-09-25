"""Tests for the public registry API of the pydantic v1 models.

The v1 models keep their own ``_types`` / ``_controller_types`` mappings, so
they need the same public entry points as the v2 module, operating on those
registries.
"""

import pytest
from pydantic.v1 import BaseModel  # noqa: F401

from oold.model import BaseController
from oold.model.v1 import (
    LinkedBaseModel,
    _controller_types,
    _types,
    find_controller_type,
    get_registered_controller_types,
    get_registered_type,
    register_controller_type,
    register_type,
    registered_controller_types,
    registered_types,
)


class V1Model(LinkedBaseModel):
    id: str = "x"
    type: str = "ex:V1RegModel"


class V1Controller(BaseController, V1Model):
    pass


def test_models_register_themselves_on_creation():
    assert get_registered_type("ex:V1RegModel") is V1Model


def test_controllers_register_themselves_on_creation():
    assert V1Controller in get_registered_controller_types("ex:V1RegModel")


def test_controllers_do_not_shadow_the_data_model():
    assert get_registered_type("ex:V1RegModel") is V1Model


def test_registries_are_separate_from_the_v2_ones():
    from oold import model as v2_model

    assert registered_types() is _types
    assert registered_controller_types() is _controller_types
    assert _types is not v2_model._types
    assert _controller_types is not v2_model._controller_types


def test_register_type_with_explicit_iri():
    dyn = type("V1RegDyn", (V1Model,), {})
    register_type(dyn, "ex:V1RegAlias")
    assert get_registered_type("ex:V1RegAlias") is dyn


def test_register_controller_type_with_explicit_iri():
    dyn = type("V1CtrlDyn", (V1Controller,), {})
    register_controller_type(dyn, "ex:V1CtrlAlias")
    assert get_registered_controller_types("ex:V1CtrlAlias") == [dyn]


def test_register_controller_type_is_idempotent():
    register_controller_type(V1Controller)
    registered = get_registered_controller_types("ex:V1RegModel")
    assert registered.count(V1Controller) == 1


def test_unknown_iri_returns_empty_list():
    assert get_registered_controller_types("ex:V1NeverRegistered") == []


def test_class_without_iri_raises_clearly():
    with pytest.raises(ValueError, match="no type IRI"):
        register_controller_type(type("V1CtrlNoIri", (object,), {}))


def test_find_controller_type_filters_by_base():
    iri = "ex:V1FindCtrl"
    dyn = type("V1FindCtrl", (V1Controller,), {})
    register_controller_type(dyn, iri)
    assert find_controller_type(iri, base=BaseController) is dyn

    class Unrelated:
        pass

    assert find_controller_type(iri, base=Unrelated) is None


def test_find_controller_type_returns_none_for_unknown_iri():
    assert find_controller_type("ex:V1NeverRegistered") is None
