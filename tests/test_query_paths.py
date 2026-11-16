"""Attribute chaining: ``Person.address.city == "x"`` builds a dotted Condition.

Only fields that embed a model chain. Links are IRI references and lists are not
indexed, so both say so instead of failing with a bare AttributeError.
"""

import pytest
from pydantic import BaseModel
from pydantic.v1 import BaseModel as BaseModelV1

from oold.backend.interface import Condition
from oold.model._descriptor import Link, LinkedBaseModel, OoldField
from oold.model.v1 import LinkedBaseModel as LinkedBaseModelV1


class Geo(BaseModel):
    lat: float | None = None


class Address(BaseModel):
    city: str | None = None
    # names the proxy itself carries: chaining must win over them
    name: str | None = None
    default: str | None = None
    field: str | None = None
    geo: Geo | None = None


class Org(LinkedBaseModel):
    id: str


class Person(LinkedBaseModel):
    id: str
    type: str | None = "qpaths:Person"
    name: str | None = None
    address: Address | None = None
    home: Address
    previous: list[Address] | None = None
    employer: Link["Org | None"] = OoldField()


class GeoV1(BaseModelV1):
    lat: float | None = None


class AddressV1(BaseModelV1):
    city: str | None = None
    name: str | None = None
    geo: GeoV1 | None = None


class PersonV1(LinkedBaseModelV1):
    id: str
    name: str | None = None
    address: AddressV1 | None = None
    previous: list[AddressV1] | None = None


def _assert_condition(condition, field, operator, value):
    assert isinstance(condition, Condition)
    assert (condition.field, condition.operator, condition.value) == (field, operator, value)


def test_chaining_builds_a_dotted_field():
    _assert_condition(Person.address.city == "Berlin", "address.city", "eq", "Berlin")
    _assert_condition(Person.home.city == "Berlin", "home.city", "eq", "Berlin")


@pytest.mark.parametrize(
    ("build", "operator"),
    [
        (lambda: Person.address.geo.lat == 1.5, "eq"),
        (lambda: Person.address.geo.lat != 1.5, "ne"),
        (lambda: Person.address.geo.lat < 1.5, "lt"),
        (lambda: Person.address.geo.lat <= 1.5, "le"),
        (lambda: Person.address.geo.lat > 1.5, "gt"),
        (lambda: Person.address.geo.lat >= 1.5, "ge"),
    ],
)
def test_chaining_goes_deeper_and_keeps_every_operator(build, operator):
    _assert_condition(build(), "address.geo.lat", operator, 1.5)


@pytest.mark.parametrize("attribute", ["name", "default", "field"])
def test_nested_fields_named_like_the_proxy_attributes_still_chain(attribute):
    condition = getattr(Person.address, attribute) == "x"

    _assert_condition(condition, f"address.{attribute}", "eq", "x")


def test_a_top_level_field_is_unchanged():
    _assert_condition(Person.name == "Ada", "name", "eq", "Ada")
    assert Person.type.startswith("qpaths:")  # forwards to the default, as before
    assert not Person.address


def test_chained_conditions_combine():
    query = (Person.address.city == "Berlin") & (Person.home.city == "Paris")

    assert (query.op1.field, query.op2.field) == ("address.city", "home.city")


def test_an_unknown_nested_field_is_an_attribute_error():
    with pytest.raises(AttributeError):
        Person.address.nothing  # noqa: B018


def test_a_list_of_models_does_not_chain():
    with pytest.raises(AttributeError, match="list of models"):
        Person.previous.city  # noqa: B018


def test_a_link_does_not_chain():
    with pytest.raises(AttributeError, match="is a link"):
        Person.employer.id  # noqa: B018


def test_a_link_can_still_be_compared_with_an_iri():
    _assert_condition(Person.employer == "ex:org1", "employer", "eq", "ex:org1")


def test_chaining_works_for_pydantic_v1_models():
    _assert_condition(PersonV1.address.city == "Berlin", "address.city", "eq", "Berlin")
    _assert_condition(PersonV1.address.name == "x", "address.name", "eq", "x")
    _assert_condition(PersonV1.address.geo.lat > 1, "address.geo.lat", "gt", 1)
    with pytest.raises(AttributeError, match="list of models"):
        PersonV1.previous.city  # noqa: B018


def test_the_legacy_binding_names_the_descriptor_binding():
    from oold.model import _LinkedBaseModelLegacy

    class LegacyPerson(_LinkedBaseModelLegacy):
        id: str
        label: str = "abc"
        address: Address | None = None

    assert LegacyPerson.label.upper() == "ABC"  # not a path: still forwards to the default
    with pytest.raises(NotImplementedError, match="descriptor binding"):
        LegacyPerson.address.city  # noqa: B018


def test_the_legacy_v1_binding_names_the_descriptor_binding():
    from oold.model.v1 import _LinkedBaseModelLegacy

    class LegacyPersonV1(_LinkedBaseModelLegacy):
        id: str
        label: str = "abc"
        address: AddressV1 | None = None

    assert LegacyPersonV1.label.upper() == "ABC"  # not a path: still forwards to the default
    with pytest.raises(NotImplementedError, match="descriptor binding"):
        LegacyPersonV1.address.city  # noqa: B018


def test_paths_helpers_tolerate_a_missing_field_and_an_unhashable_annotation():
    from oold.model._paths import embedded_model, is_model_container

    class Unhashable:
        __hash__ = None  # type: ignore[assignment]

    class FieldWithUnhashableAnnotation:
        annotation = Unhashable()

    assert embedded_model(None) is None
    assert is_model_container(None) is False
    assert embedded_model(FieldWithUnhashableAnnotation()) is None
