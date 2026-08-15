"""Tests for the reviewed link declaration notations.

Type IRIs are prefixed ``ex:N...`` so they do not collide with other test
modules: the class registry used for polymorphic resolution is process-wide
and keyed by type IRI, so two classes claiming the same IRI shadow each other.

Covers the notations proposed in the oold-python#107 review:
``OoldField()`` / ``link=True`` with the target inferred from the annotation,
``Link[T]`` used *inside* an annotation, and union arms mixing a literal, an
inline object and a reference.
"""

from typing import List, Optional, Union

import pytest
from pydantic import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.experimental.notation import Link, OoldField, OoldModel


class Org(OoldModel):
    id: str
    name: Optional[str] = None
    type: Optional[str] = "ex:NOrg"


class Location(OoldModel):
    id: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = "ex:NLoc"


class Person(OoldModel):
    id: str
    name: Optional[str] = None
    type: Optional[str] = "ex:NPerson"
    # target inferred from the annotation, no range= needed
    knows: Optional[List["Person"]] = OoldField()
    # Link[T] inside the annotation
    employer: Optional[Link[Org]] = Field(default=None)
    friends: Optional[List[Link["Person"]]] = OoldField()
    # union: literal text | inline object | reference
    location: Union[str, Location, None] = OoldField(link=True)


Person.model_rebuild()


@pytest.fixture()
def store():
    s = SimpleDictDocumentStore()
    s.store_json_dicts(
        {
            "ex:p2": {"id": "ex:p2", "name": "Bob", "type": "ex:NPerson"},
            "ex:acme": {"id": "ex:acme", "name": "ACME", "type": "ex:NOrg"},
            "ex:loc": {
                "id": "ex:loc",
                "address": "Champ de Mars",
                "type": "ex:NLoc",
            },
        }
    )
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def test_all_notations_register_as_links():
    assert set(Person.__link_fields__) == {"knows", "employer", "friends", "location"}


def test_oold_field_without_arguments(store):
    p = Person(id="ex:p1", knows=["ex:p2"])
    assert isinstance(p.knows[0], Person)
    assert p.knows[0].name == "Bob"
    assert p.model_dump(exclude_none=True)["knows"] == ["ex:p2"]


def test_link_inside_annotation(store):
    p = Person(id="ex:p1", employer="ex:acme", friends=["ex:p2"])
    assert isinstance(p.employer, Org) and p.employer.name == "ACME"
    assert isinstance(p.friends[0], Person) and p.friends[0].name == "Bob"
    d = p.model_dump(exclude_none=True)
    assert d["employer"] == "ex:acme"
    assert d["friends"] == ["ex:p2"]


def test_union_literal_arm(store):
    p = Person(id="ex:a", location="at the Eiffel Tower")
    assert p.location == "at the Eiffel Tower"
    assert p.model_dump(exclude_none=True)["location"] == "at the Eiffel Tower"


def test_union_reference_arm(store):
    p = Person(id="ex:b", location={"@id": "ex:loc"})
    assert isinstance(p.location, Location)
    assert p.location.address == "Champ de Mars"
    assert p.model_dump(exclude_none=True)["location"] == "ex:loc"


def test_union_inline_arm_with_id(store):
    p = Person(
        id="ex:c",
        location={"id": "ex:inline", "address": "inline addr", "type": "ex:NLoc"},
    )
    assert isinstance(p.location, Location) and p.location.address == "inline addr"
    # it carries an IRI, so it serialises as a reference
    assert p.model_dump(exclude_none=True)["location"] == "ex:inline"


def test_union_inline_without_id_is_a_blank_node(store):
    p = Person(id="ex:d", location={"address": "no id here", "type": "ex:NLoc"})
    assert isinstance(p.location, Location)
    assert p.link_iris("location") is None
    dumped = p.model_dump(exclude_none=True)["location"]
    # no IRI to reference, so the object stays nested
    assert isinstance(dumped, dict) and dumped["address"] == "no id here"


def test_mutation(store):
    p = Person(id="ex:p1", knows=["ex:p2"])
    p.knows = []
    assert p.knows == []
    p.knows = ["ex:p2"]
    assert p.knows[0].name == "Bob"


def test_query_dsl_still_available():
    cond = Person.name == "John"
    assert cond.field == "name"
    assert Person[cond] is not None
