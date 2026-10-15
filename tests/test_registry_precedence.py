"""Precedence and isolation of the type registries.

Three accessors read the controller registry - ``get_registered_controller_types``,
``find_controller_type`` and ``resolve_type`` - and they used to disagree: the
first returned earliest-first, the second last-first, and the third refused to
resolve at all once a second controller was registered, which turned the
documented override mechanism into a way of disabling controllers. The rule is
now one: the controller registered last wins, in every accessor.

The second rule is that the two pydantic layers never mix. A v2 class handed to
v1 deserialization does not validate, so resolution has to stay in the layer the
model registry belongs to.
"""

import logging

import pytest
from pydantic import ConfigDict

from oold.model import (
    BaseController,
    LinkedBaseModel,
    _types,
    find_controller_type,
    get_registered_controller_types,
    register_controller_type,
    register_type,
)
from oold.static import resolve_type

IRI = "Category:OSWPrecedenceModel"


class PrecedenceModel(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"title": "PrecedenceModel"})
    type: list[str] | None = [IRI]


class FirstController(BaseController, PrecedenceModel):
    pass


class SecondController(BaseController, PrecedenceModel):
    pass


# -- the three accessors agree ------------------------------------------------


def test_accessors_agree_on_the_last_registration():
    registered = get_registered_controller_types(IRI)
    assert registered[0] is SecondController
    assert find_controller_type(IRI) is registered[0]
    assert resolve_type(IRI, _types) is registered[0]


def test_a_later_registration_takes_over():
    third = type("ThirdController", (FirstController,), {})
    register_controller_type(third, IRI)
    assert get_registered_controller_types(IRI)[0] is third
    assert find_controller_type(IRI) is third
    assert resolve_type(IRI, _types) is third


def test_re_registering_moves_a_controller_to_the_front():
    register_controller_type(FirstController, IRI)
    assert resolve_type(IRI, _types) is FirstController
    assert get_registered_controller_types(IRI).count(FirstController) == 1


def test_prefer_controller_false_still_gives_the_pure_model():
    assert resolve_type(IRI, _types, prefer_controller=False) is PrecedenceModel


# -- the layers stay apart ----------------------------------------------------


def test_v1_registration_does_not_leak_into_v2():
    from oold.model.v1 import BaseController as BaseControllerV1
    from oold.model.v1 import LinkedBaseModel as LinkedBaseModelV1
    from oold.model.v1 import _types as _types_v1

    class SharedIriModelV1(LinkedBaseModelV1):
        class Config:
            schema_extra = {"title": "SharedIriModelV1"}

        type: list = [IRI]

    class SharedIriControllerV1(BaseControllerV1, SharedIriModelV1):
        pass

    assert resolve_type(IRI, _types_v1) is SharedIriControllerV1
    assert resolve_type(IRI, _types) is SecondController


def test_explicit_registry_argument_wins_over_inference():
    assert resolve_type(IRI, _types, _controller_types={}) is PrecedenceModel


# -- registrations are reported -----------------------------------------------


def test_override_is_warned_about(caplog):
    iri = "Category:OSWWarnOverride"
    first = type("WarnFirst", (FirstController,), {})
    second = type("WarnSecond", (FirstController,), {})
    register_controller_type(first, iri)
    with caplog.at_level(logging.WARNING, logger="oold.model"):
        register_controller_type(second, iri)
    assert "WarnSecond" in caplog.text
    assert "WarnFirst" in caplog.text


def test_first_registration_is_logged_at_info(caplog):
    iri = "Category:OSWInfoOnce"
    # created outside the capture: a subclass registers under the inherited IRI
    # on creation, which is itself an override of the controllers already there
    dyn = type("InfoOnce", (FirstController,), {})
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="oold.model"):
        register_controller_type(dyn, iri)
    assert iri in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_replacing_a_model_is_warned_about(caplog):
    iri = "Category:OSWModelReplaced"
    register_type(PrecedenceModel, iri)
    with caplog.at_level(logging.WARNING, logger="oold.model"):
        register_type(type("Replacement", (PrecedenceModel,), {}), iri)
    assert "Replacement" in caplog.text


# -- the public API flattens and validates like the metaclass -----------------


def test_register_type_flattens_a_nested_iri_list():
    dyn = type("NestedIriModel", (PrecedenceModel,), {})
    register_type(dyn, [["Category:OSWNestedA"], "Category:OSWNestedB"])
    assert _types["Category:OSWNestedA"] is dyn
    assert _types["Category:OSWNestedB"] is dyn


@pytest.mark.parametrize("iri", [[], "", ["", None]])
def test_register_type_rejects_an_unusable_iri(iri):
    dyn = type("UnusableIriModel", (PrecedenceModel,), {})
    with pytest.raises(ValueError, match="no usable type IRI"):
        register_type(dyn, iri)


def test_register_type_skips_an_inherited_iri():
    """A subclass that only narrows a field must not replace its parent."""

    class NarrowedModel(PrecedenceModel):
        extra: str = "x"

    register_type(NarrowedModel)
    assert _types[IRI] is PrecedenceModel


def test_v1_register_type_skips_an_inherited_iri():
    from oold.model.v1 import LinkedBaseModel as LinkedBaseModelV1
    from oold.model.v1 import _types as _types_v1
    from oold.model.v1 import register_type as register_type_v1

    v1_iri = "Category:OSWV1InheritGuard"

    class V1Parent(LinkedBaseModelV1):
        class Config:
            schema_extra = {"title": "V1Parent"}

        type: list = [v1_iri]

    class V1Child(V1Parent):
        extra: str = "x"

    register_type_v1(V1Child)
    assert _types_v1[v1_iri] is V1Parent
