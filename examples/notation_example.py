"""Smoke test for the reviewed link declaration notations.

Runnable end-to-end and self-checking, so it doubles as a copy-paste starting
point. Covers the notations discussed in oold-python#107:

1. ``OoldField()`` with no arguments - the link target is inferred from the
   annotation, so the schema IRI is not repeated in Python.
2. ``Link[T]`` **inside** an annotation, to-one and inside ``List[...]``.
3. **Union arms** mixing a literal, an inline object and a reference.

Run it:

    python examples/notation_example.py

The recommended variant for generated code is
``oold.experimental.auto_descriptor_binding`` (unchanged declaration syntax);
``oold.experimental.notation`` adds the notations above on top of it.
"""

# ruff: noqa: S101  - assertions are this script's purpose

from pydantic import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.experimental.notation import Link, OoldField, OoldModel


class Organization(OoldModel):
    id: str
    name: str | None = None
    type: str | None = "ex:Organization"


class Location(OoldModel):
    id: str | None = None  # optional: an inline value may be a blank node
    address: str | None = None
    type: str | None = "ex:Location"


class Person(OoldModel):
    id: str
    name: str | None = None
    type: str | None = "ex:Person"

    # 1. no range= needed: the target is read from the annotation
    knows: list["Person"] | None = OoldField()

    # 2. Link[T] inside the annotation (to-one and to-many)
    employer: Link[Organization] | None = Field(default=None)
    friends: list[Link["Person"]] | None = OoldField()

    # 3. union: literal text | inline object | reference
    location: str | Location | None = OoldField(link=True)


Person.model_rebuild()


def setup_backend() -> SimpleDictDocumentStore:
    store = SimpleDictDocumentStore()
    store.store_json_dicts({
        "ex:bob": {"id": "ex:bob", "name": "Bob", "type": "ex:Person"},
        "ex:carol": {"id": "ex:carol", "name": "Carol", "type": "ex:Person"},
        "ex:acme": {"id": "ex:acme", "name": "ACME", "type": "ex:Organization"},
        "ex:eiffel": {
            "id": "ex:eiffel",
            "address": "Champ de Mars",
            "type": "ex:Location",
        },
    })
    set_resolver(SetResolverParam(iri="ex", resolver=store))
    return store


def main() -> None:
    setup_backend()

    alice = Person(
        id="ex:alice",
        name="Alice",
        knows=["ex:bob", "ex:carol"],  # by IRI, resolved on demand
        employer="ex:acme",
        friends=[Person(id="ex:bob", name="Bob")],  # or by object
    )

    print("1. OoldField() - target inferred from the annotation")
    assert alice.knows[0].name == "Bob"
    assert isinstance(alice.knows[0], Person)  # a real Person, not a proxy
    print("   knows[0].name          =", alice.knows[0].name)
    print("   isinstance(.., Person) =", isinstance(alice.knows[0], Person))

    print("\n2. Link[T] inside the annotation")
    assert isinstance(alice.employer, Organization)
    assert alice.employer.name == "ACME"
    assert isinstance(alice.friends[0], Person)
    print("   employer.name          =", alice.employer.name)
    print("   friends[0].name        =", alice.friends[0].name)

    print("\n3. union arms: text | inline object | reference")
    text = Person(id="ex:p-text", location="at the Eiffel Tower")
    ref = Person(id="ex:p-ref", location={"@id": "ex:eiffel"})
    inline = Person(
        id="ex:p-inline",
        location={"id": "ex:office", "address": "Main St 1", "type": "ex:Location"},
    )
    blank = Person(id="ex:p-blank", location={"address": "no id", "type": "ex:Location"})

    assert text.location == "at the Eiffel Tower"  # stays a literal
    assert isinstance(ref.location, Location)  # resolved reference
    assert ref.location.address == "Champ de Mars"
    assert inline.location.address == "Main St 1"
    assert blank.link_iris("location") is None  # no IRI -> blank node
    print("   text   ->", repr(text.location))
    print("   ref    ->", ref.location.address)
    print("   inline ->", inline.location.address)
    print("   blank  ->", blank.location.address, "(no IRI)")

    print("\n4. serialisation: links collapse to IRIs, blank nodes stay nested")
    dumped = alice.model_dump(exclude_none=True)
    assert dumped["knows"] == ["ex:bob", "ex:carol"]
    assert dumped["employer"] == "ex:acme"
    assert ref.model_dump(exclude_none=True)["location"] == "ex:eiffel"
    assert isinstance(blank.model_dump(exclude_none=True)["location"], dict)
    print("   alice ->", dumped)
    print("   ref   ->", ref.model_dump(exclude_none=True))
    print("   blank ->", blank.model_dump(exclude_none=True))

    print("\n5. lazy resolution and query DSL")
    lazy = Person(id="ex:lazy", knows=["ex:bob"])
    assert lazy.link_iris("knows") == ["ex:bob"]  # inspect without resolving
    condition = Person.name == "Bob"
    assert condition.field == "name" and condition.value == "Bob"
    print("   link_iris('knows')     =", lazy.link_iris("knows"))
    print("   Person.name == 'Bob'   =", condition)

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
