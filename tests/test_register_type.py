"""Tests for the public type-registry API.

Downstream currently imports the private ``_types`` mapping and writes into it
(7 sites across the generated packages and applications), because no public
entry point existed. These functions are that entry point; ``_types`` stays as
the live mapping so existing callers keep working.
"""

import pytest

from oold.model import (
    LinkedBaseModel,
    _types,
    get_registered_type,
    register_type,
    registered_types,
)


class Thing(LinkedBaseModel):
    id: str
    type: str | None = "ex:RegThing"


def test_classes_register_themselves_on_creation():
    assert get_registered_type("ex:RegThing") is Thing


def test_register_type_with_explicit_iri():
    """The dynamic-class case that forced downstream to poke at _types."""
    dyn = type("RegDyn", (Thing,), {})
    register_type(dyn, "ex:RegAlias")
    assert get_registered_type("ex:RegAlias") is dyn


def test_register_type_defaults_to_get_cls_iri():
    register_type(Thing)  # idempotent
    assert get_registered_type("ex:RegThing") is Thing


def test_register_type_accepts_a_list_of_iris():
    dyn = type("RegMulti", (Thing,), {})
    register_type(dyn, ["ex:RegA", "ex:RegB"])
    assert get_registered_type("ex:RegA") is dyn
    assert get_registered_type("ex:RegB") is dyn


def test_registry_identity_is_shared():
    """Resolution reads this mapping, so identity matters, not a copy."""
    assert registered_types() is _types


def test_unknown_iri_returns_none():
    assert get_registered_type("ex:NeverRegistered") is None


def test_class_without_iri_raises_clearly():
    with pytest.raises(ValueError, match="no type IRI"):
        register_type(type("RegNoIri", (object,), {}))
