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


# -- opting out of the registries --


def test_a_class_can_opt_out_of_registration():
    """``InMemoryController`` over a local-file model is the case for it."""
    iri = "Category:OSWOptOut"

    class OptOutModel(LinkedBaseModel):
        model_config = ConfigDict(json_schema_extra={"title": "OptOutModel"})
        type: list[str] | None = [iri]

    class OptOutController(BaseController, OptOutModel):
        __oold_register__ = False

    assert get_registered_controller_types(iri) == []
    assert resolve_type(iri, _types) is OptOutModel
    assert OptOutController(OptOutModel()).type == [iri]


def test_opting_out_still_allows_an_explicit_registration():
    iri = "Category:OSWOptOutExplicit"

    class ExplicitModel(LinkedBaseModel):
        model_config = ConfigDict(json_schema_extra={"title": "ExplicitModel"})
        type: list[str] | None = [iri]

    class ExplicitController(BaseController, ExplicitModel):
        __oold_register__ = False

    register_controller_type(ExplicitController, iri)
    assert resolve_type(iri, _types) is ExplicitController


# -- the v1 layer answers the same way ----------------------------------------


def _v1_controller(iri):
    """A v1 model with a controller on it, registered under ``iri``."""
    from oold.model.v1 import BaseController as BaseControllerV1
    from oold.model.v1 import LinkedBaseModel as LinkedBaseModelV1

    class Model(LinkedBaseModelV1):
        class Config:
            schema_extra = {"title": "V1PrecedenceModel"}

        type: list = [iri]

    class First(BaseControllerV1, Model):
        pass

    class Second(BaseControllerV1, Model):
        pass

    return Model, First, Second


def test_v1_accessors_agree_on_the_last_registration():
    from oold.model.v1 import _types as _types_v1
    from oold.model.v1 import find_controller_type as find_v1
    from oold.model.v1 import get_registered_controller_types as registered_v1

    iri = "Category:OSWV1Precedence"
    model, _first, second = _v1_controller(iri)

    assert registered_v1(iri)[0] is second
    assert find_v1(iri) is second
    assert resolve_type(iri, _types_v1) is second
    assert resolve_type(iri, _types_v1, prefer_controller=False) is model


def test_v1_class_can_opt_out_of_registration():
    from oold.model.v1 import BaseController as BaseControllerV1
    from oold.model.v1 import LinkedBaseModel as LinkedBaseModelV1
    from oold.model.v1 import _types as _types_v1
    from oold.model.v1 import get_registered_controller_types as registered_v1

    iri = "Category:OSWV1OptOut"

    class Model(LinkedBaseModelV1):
        class Config:
            schema_extra = {"title": "V1OptOutModel"}

        type: list = [iri]

    class OptedOut(BaseControllerV1, Model):
        __oold_register__ = False

    assert registered_v1(iri) == []
    assert resolve_type(iri, _types_v1) is Model
    assert OptedOut(Model()).type == [iri]


# -- a reloaded module is not an override -------------------------------------


def test_re_registering_the_same_class_does_not_pile_up(caplog):
    """A regenerated model module re-runs every class body."""
    iri = "Category:OSWReloaded"

    def make():
        class ReloadedModel(LinkedBaseModel):
            model_config = ConfigDict(json_schema_extra={"title": "ReloadedModel"})
            type: list[str] | None = [iri]

        class ReloadedController(BaseController, ReloadedModel):
            pass

        return ReloadedController

    make()
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="oold.model"):
        make()
    assert len(get_registered_controller_types(iri)) == 1
    assert not caplog.records


def test_an_unusable_iri_next_to_a_usable_one_does_not_break_registration():
    """get_cls_iri() may return the default of a required field."""
    dyn = type("MixedIriModel", (PrecedenceModel,), {})
    register_type(dyn, ["Category:OSWMixedUsable", object()])
    assert _types["Category:OSWMixedUsable"] is dyn
