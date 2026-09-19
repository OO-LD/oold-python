"""Tests for the reviewed link declaration notations.

Type IRIs are prefixed ``ex:N...`` so they do not collide with other test
modules: the class registry used for polymorphic resolution is process-wide
and keyed by type IRI, so two classes claiming the same IRI shadow each other.

Covers the notations proposed in the oold-python#107 review:
``OoldField()`` / ``link=True`` with the target inferred from the annotation,
``Link[T]`` used *inside* an annotation, and union arms mixing a literal, an
inline object and a reference.
"""

import pytest
from pydantic import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model import LinkNotResolved
from oold.model._notation import Link, OoldField, OoldModel


class Org(OoldModel):
    id: str
    name: str | None = None
    type: str | None = "ex:NOrg"


class Location(OoldModel):
    id: str | None = None
    address: str | None = None
    type: str | None = "ex:NLoc"


class Person(OoldModel):
    id: str
    name: str | None = None
    type: str | None = "ex:NPerson"
    # target inferred from the annotation, no range= needed
    knows: list["Person"] = OoldField()
    # Link[T] inside the annotation
    employer: Link[Org] | None = Field(default=None)
    friends: list[Link["Person"]] = OoldField()
    # union: literal text | inline object | reference
    location: str | Location | None = OoldField(link=True)


Person.model_rebuild()


@pytest.fixture()
def store():
    s = SimpleDictDocumentStore()
    s.store_json_dicts({
        "ex:p2": {"id": "ex:p2", "name": "Bob", "type": "ex:NPerson"},
        "ex:acme": {"id": "ex:acme", "name": "ACME", "type": "ex:NOrg"},
        "ex:loc": {
            "id": "ex:loc",
            "address": "Champ de Mars",
            "type": "ex:NLoc",
        },
    })
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
    # the field also accepts a literal, so a reference must be boxed as
    # {"@id": ...} - a bare IRI would be re-read as text
    assert p.model_dump(exclude_none=True)["location"] == {"@id": "ex:loc"}


def test_union_inline_arm_with_id(store):
    p = Person(
        id="ex:c",
        location={"id": "ex:inline", "address": "inline addr", "type": "ex:NLoc"},
    )
    assert isinstance(p.location, Location) and p.location.address == "inline addr"
    # it carries an IRI, so it serialises as a (boxed) reference
    assert p.model_dump(exclude_none=True)["location"] == {"@id": "ex:inline"}


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


def test_query_dsl_still_available(store):
    """Runs the real query, not a stub.

    ``OoldModel.oold_query`` used to return ``("query", cls.__name__, item)``
    unconditionally, so asserting ``is not None`` here could never fail and no
    backend was ever consulted.
    """
    cond = Person.name == "Bob"
    assert cond.field == "name"
    found = Person[cond]
    assert found is not None
    assert [p.id for p in found] == ["ex:p2"]
    assert Person[Person.name == "nobody-by-that-name"] is None


def test_union_round_trip_preserves_every_arm(store):
    """Deserialisation is the hard part: each arm must survive a round trip."""
    cases = {
        "text": ("at the Eiffel Tower", str),
        "reference": ({"@id": "ex:loc"}, Location),
        "inline": ({"address": "Main St", "type": "ex:NLoc"}, Location),
    }
    for label, (value, expected) in cases.items():
        original = Person(id="ex:rt", location=value)
        restored = Person(**original.model_dump(exclude_none=True))
        assert isinstance(restored.location, expected), label
        if expected is str:
            assert restored.location == original.location, label
        else:
            assert restored.location.address == original.location.address, label


def test_round_trip_without_literal_arm_keeps_bare_iri(store):
    """With no literal arm a bare IRI is unambiguous, so it stays compact."""
    p = Person(id="ex:p1", employer="ex:acme")
    dumped = p.model_dump(exclude_none=True)
    assert dumped["employer"] == "ex:acme"  # not boxed
    restored = Person(**dumped)
    assert isinstance(restored.employer, Org)
    assert restored.employer.name == "ACME"


def test_round_trip_list_of_links(store):
    p = Person(id="ex:p1", knows=["ex:p2"], friends=["ex:p2"])
    restored = Person(**p.model_dump(exclude_none=True))
    assert [x.id for x in restored.knows] == ["ex:p2"]
    assert [x.id for x in restored.friends] == ["ex:p2"]
    assert isinstance(restored.knows[0], Person)


def test_equality_is_independent_of_resolution(store):
    """Reading a link caches it in __dict__; that must not change equality."""
    a = Person(id="ex:p1", knows=["ex:p2"])
    b = Person(id="ex:p1", knows=["ex:p2"])
    _ = a.knows  # resolve on one side only
    assert a == b
    assert Person(id="ex:p1", knows=["ex:p2"]) != Person(id="ex:p1")
    assert Person(id="ex:p1") != Person(id="ex:other")


def test_unset_and_explicit_empty_are_distinct(store):
    """Unset contributes nothing; an explicit [] is a statement and round-trips."""
    unset = Person(id="ex:u").model_dump(exclude_none=True)
    empty = Person(id="ex:e", knows=[]).model_dump(exclude_none=True)
    assert "knows" not in unset
    assert empty["knows"] == []
    assert Person(**empty).model_dump(exclude_none=True)["knows"] == []


def test_unset_to_many_reads_as_empty_list(store):
    """A non-Optional list annotation must not hand back None."""
    p = Person(id="ex:u")
    assert p.knows == []
    assert p.employer is None  # to-one keeps None, and keeps "| None"


def _required(model_cls) -> list:
    schema = model_cls.model_json_schema()
    if "properties" in schema:
        return schema.get("required", [])
    return schema["$defs"][model_cls.__name__].get("required", [])


def _properties(model_cls) -> dict:
    schema = model_cls.model_json_schema()
    if "properties" in schema:
        return schema["properties"]
    return schema["$defs"][model_cls.__name__]["properties"]


def test_range_is_derived_from_the_annotation():
    """Presence of ``x-oold-range`` is what makes a property a link, so the
    annotation has to put it there - otherwise the recommended declaration
    emits a schema that does not round-trip through code generation, and the
    only way to get one is to repeat the target in ``OoldField(range=...)``."""
    props = _properties(Person)
    assert props["knows"]["x-oold-range"] == Person.get_cls_iri()
    assert props["friends"]["x-oold-range"] == Person.get_cls_iri()
    assert props["employer"]["x-oold-range"] == Org.get_cls_iri()
    assert props["location"]["x-oold-range"] == Location.get_cls_iri()
    # the marker was a stand-in for the range; it goes once the range is there
    assert "x-oold-link" not in props["knows"]


def test_an_explicit_range_is_not_overwritten():
    class Explicit(OoldModel):
        id: str
        type: str | None = "ex:NExplicit"
        target: Link[Org] = OoldField(range="Legacy.json")

    Explicit.model_rebuild()
    assert _properties(Explicit)["target"]["x-oold-range"] == "Legacy.json"


def test_required_is_a_field_argument_not_the_annotation():
    """Requiredness and the read type are separate questions. A self-link needs
    them to differ: father reads as a Person so a walk needs no guard per hop,
    while no real dataset can require every person to name one."""

    class Chain(OoldModel):
        id: str
        type: str | None = "ex:NChain"
        father: Link["Chain"] = OoldField()
        manager: Link["Org"] = OoldField(required=True)

    Chain.model_rebuild()

    with pytest.raises(ValueError, match="manager is required"):
        Chain(id="ex:c")
    c = Chain(id="ex:c", manager="ex:acme")
    with pytest.raises(LinkNotResolved):
        _ = c.father  # optional to supply, still mandatory to read

    # the schema states requiredness through `required` and nothing else;
    # x-oold-required-iri is an oold-python field annotation and stays internal
    assert "manager" in _required(Chain)
    assert "father" not in _required(Chain)
    assert "x-oold-required-iri" not in _properties(Chain)["manager"]
    assert Chain.__link_fields__["manager"].required_iri is True


def test_required_iri_is_still_accepted():
    """Generated packages pass the old spelling."""

    class Old(OoldModel):
        id: str
        type: str | None = "ex:NOld"
        manager: Link["Org"] = OoldField(required_iri=True)

    Old.model_rebuild()
    with pytest.raises(ValueError, match="manager is required"):
        Old(id="ex:o")
    assert "manager" in _required(Old)
    assert Old.__link_fields__["manager"].required_iri is True


def test_a_link_annotation_without_a_default_is_optional():
    """Links are declared far more often than they are required, so the terse
    form is the common case.

    Requiredness is explicit because it propagates into resolution: resolving a
    link constructs the target, so a required link makes every stored document
    lacking it unconstructible - and a self-referential link, `father`, could
    then never be satisfied by a real dataset.
    """

    class Bare(OoldModel):
        id: str
        type: str | None = "ex:NBare"
        manager: Link["Org"]

    Bare.model_rebuild()
    assert Bare(id="ex:b").link_iris("manager") is None  # constructs unset
    assert Bare(id="ex:b", manager="ex:acme").link_iris("manager") == "ex:acme"
    assert Bare.__link_fields__["manager"].required_iri is False
