"""``Link[T]`` / ``LinkList[T]`` used as the whole annotation.

The static half of this contract lives in ``tests/typing/links.py``; here is the
runtime half, which has to be indistinguishable from the plain spelling: same
schema, same resolution, same serialisation. The annotation only adds what a type
checker can see.
"""

import pytest
from pydantic import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model._descriptor import AutoLinkedModel, Link, LinkList, OoldField


class Org(AutoLinkedModel):
    id: str
    name: str | None = None
    type: str | None = "annot:Organization"


class Person(AutoLinkedModel):
    id: str
    name: str | None = None
    type: str | None = "annot:Person"
    knows: LinkList["Person"] = OoldField()
    employer: Link[Org] = OoldField()
    mixed: LinkList["Person | Org"] = OoldField()


class Plain(AutoLinkedModel):
    id: str
    type: str | None = "annot:Plain"
    knows: list["Person"] | None = Field(None, json_schema_extra={"range": "Person"})


Person.model_rebuild()
Plain.model_rebuild()


@pytest.fixture
def store():
    store = SimpleDictDocumentStore()
    store.store_json_dicts({
        "annot:bob": {"id": "annot:bob", "name": "Bob", "type": "annot:Person"},
        "annot:acme": {"id": "annot:acme", "name": "ACME", "type": "annot:Organization"},
    })
    set_resolver(SetResolverParam(iri="annot", resolver=store))
    return store


def test_annotation_alone_declares_the_link():
    """No range= and no x-oold-link needed: the annotation says it."""
    assert set(Person.__link_fields__) == {"knows", "employer", "mixed"}
    assert Person.__link_fields__["knows"].many is True
    assert Person.__link_fields__["employer"].many is False


def test_schema_matches_the_plain_spelling():
    """Pydantic is handed the target's schema, so the output is unchanged."""

    def props(model):
        schema = model.model_json_schema()
        return schema.get("properties") or schema["$defs"][model.__name__]["properties"]

    annotated = props(Person)["knows"]
    plain = props(Plain)["knows"]
    assert annotated["type"] == "array"
    assert annotated["items"] == {"$ref": "#/$defs/Person"}
    # the plain form wraps in anyOf only because it is declared Optional
    assert plain["anyOf"][0]["items"] == {"$ref": "#/$defs/Person"}


def test_construct_by_iri_object_and_json(store):
    p = Person(
        id="annot:a",
        knows=["annot:bob", Person(id="annot:c", name="Carol"), {"id": "annot:d"}],
        employer="annot:acme",
    )
    assert [type(v).__name__ for v in p.knows] == ["Person", "Person", "Person"]
    assert p.knows[0].name == "Bob"
    assert isinstance(p.employer, Org)
    assert p.employer.name == "ACME"


def test_unresolvable_reference_reads_as_none(store):
    """An IRI the backend cannot answer keeps its slot, as None."""
    p = Person(id="annot:a", knows=["annot:bob", "annot:nobody"])
    assert len(p.knows) == 2
    assert p.knows[1] is None
    assert p.link_iris("knows") == ["annot:bob", "annot:nobody"]


def test_mixed_target_resolves_each_arm_by_type(store):
    p = Person(id="annot:a", mixed=["annot:bob", "annot:acme"])
    assert [type(v).__name__ for v in p.mixed] == ["Person", "Org"]


def test_serialises_back_to_iris(store):
    p = Person(id="annot:a", knows=["annot:bob"], employer="annot:acme")
    dumped = p.model_dump(exclude_none=True)
    assert dumped["knows"] == ["annot:bob"]
    assert dumped["employer"] == "annot:acme"


def test_explicit_descriptor_form_still_works(store):
    """The same classes remain usable as unannotated descriptors."""

    class Explicit(AutoLinkedModel):
        id: str
        type: str | None = "annot:Explicit"
        employer = Link(Org)
        knows = LinkList("Person")

    e = Explicit(id="annot:e", employer="annot:acme")
    assert isinstance(e.employer, Org)
    assert e.employer.name == "ACME"
