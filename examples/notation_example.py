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
``oold.model._descriptor`` (unchanged declaration syntax);
``oold.model._notation`` adds the notations above on top of it.
"""

from pydantic import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model._notation import Link, OoldField, OoldModel


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
    knows: list["Person"] = OoldField()

    # 2. Link[T] inside the annotation (to-one and to-many)
    employer: Link[Organization] | None = Field(default=None)
    friends: list[Link["Person"]] = OoldField()

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

    # A union field is str | Location | None, so narrow it to a local before
    # dereferencing - the same hygiene any union needs, and what lets a type
    # checker follow along.
    ref_loc, inline_loc, blank_loc = ref.location, inline.location, blank.location
    assert text.location == "at the Eiffel Tower"  # stays a literal
    assert isinstance(ref_loc, Location)  # resolved reference
    assert isinstance(inline_loc, Location) and isinstance(blank_loc, Location)
    assert ref_loc.address == "Champ de Mars"
    assert inline_loc.address == "Main St 1"
    assert blank.link_iris("location") is None  # no IRI -> blank node
    print("   text   ->", repr(text.location))
    print("   ref    ->", ref_loc.address)
    print("   inline ->", inline_loc.address)
    print("   blank  ->", blank_loc.address, "(no IRI)")

    print("\n4. serialisation: links to IRIs; references boxed where a literal arm exists")
    dumped = alice.model_dump(exclude_none=True)
    assert dumped["knows"] == ["ex:bob", "ex:carol"]
    assert dumped["employer"] == "ex:acme"
    # boxed as {"@id": ...} because the field also accepts a literal
    assert ref.model_dump(exclude_none=True)["location"] == {"@id": "ex:eiffel"}
    assert isinstance(blank.model_dump(exclude_none=True)["location"], dict)
    print("   alice ->", dumped)
    print("   ref   ->", ref.model_dump(exclude_none=True))
    print("   blank ->", blank.model_dump(exclude_none=True))

    print("\n5. lazy resolution and query DSL")
    lazy = Person(id="ex:lazy", knows=["ex:bob"])
    assert lazy.link_iris("knows") == ["ex:bob"]  # inspect without resolving
    # The class-level DSL builds a Condition at runtime, but a type checker
    # sees BaseModel.__eq__ and reads this as bool - it is not expressible in
    # the type system (see oold-python#107).
    condition = Person.name == "Bob"
    assert condition.field == "name"
    print("   link_iris('knows')     =", lazy.link_iris("knows"))
    print("   Person.name == 'Bob'   =", condition)

    print("\n6. de-serialisation: every union arm survives a round trip")
    for label, value, expected in [
        ("text     ", "at the Eiffel Tower", str),
        ("reference", {"@id": "ex:eiffel"}, Location),
        ("inline   ", {"address": "Main St 1", "type": "ex:Location"}, Location),
    ]:
        original = Person(id="ex:rt", location=value)
        payload = original.model_dump(exclude_none=True)
        restored = Person(**payload)
        assert isinstance(restored.location, expected), label
        shown = str(payload["location"])[:34]
        print(f"   {label} {shown:36} -> {type(restored.location).__name__}")

    restored = Person(**alice.model_dump(exclude_none=True))
    assert [x.id for x in restored.knows] == ["ex:bob", "ex:carol"]
    restored_employer = restored.employer  # to-one link: narrow before use
    assert restored_employer is not None and restored_employer.name == "ACME"
    print("   lists and to-one links round trip too")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
