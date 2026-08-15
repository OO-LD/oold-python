"""Example: declaring and using descriptor-based graph-object binding.

Run it:

    python examples/descriptor_binding_example.py

It shows how a model with linked (``x-oold-range``) properties is declared with
the transparent descriptor binding, and that plain attribute access returns the
REAL resolved object (so ``isinstance`` holds and autocomplete works), while
references still serialise back to IRIs.

See the design rationale in ``docs/design/graph-object-binding.md``.
"""

from __future__ import annotations

from typing import Optional

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.experimental.descriptor_binding import Link, LinkedModel, LinkList

# 1. Declare the models
#
# Plain data properties are ordinary pydantic fields (annotated).
# Link properties (an IRI-valued x-oold-range) are declared as *descriptors*,
# WITHOUT a type annotation, so pydantic never treats them as fields. Static
# typing comes from the descriptor:
#
#   Link[T](target)      -> one linked object,  read type: Optional[T]
#   LinkList[T](target)  -> many linked objects, read type: list[T]
#
# `target` is the class (when already defined) or its name as a string (for
# forward / self references). When you pass the class object, the type
# parameter is inferred and no subscript is needed:
#
#   employer  = Link(Organization)          # -> Optional[Organization]
#   addresses = LinkList(Address)           # -> list[Address]
#
# For a forward / self reference the class does not exist yet, so give the name
# and pin the type with a subscript:
#
#   knows     = LinkList["Person"]("Person")   # -> list[Person]


class Organization(LinkedModel):
    id: str
    name: Optional[str] = None


class Address(LinkedModel):
    id: str
    city: Optional[str] = None


class Person(LinkedModel):
    # plain data fields (normal pydantic)
    id: str
    name: Optional[str] = None

    # link fields (descriptors, unannotated)
    employer = Link(Organization)  # to-one, inferred Optional[Organization]
    addresses = LinkList(Address)  # to-many, inferred list[Address]
    knows = LinkList["Person"]("Person")  # self-ref, list[Person]
    best_friend = Link["Person"]("Person")  # self-ref, Optional[Person]

    @classmethod
    def ld_context(cls) -> dict:
        return {
            "ex": "https://example.org/",
            "id": "@id",
            "type": "@type",
            "name": "ex:name",
            "employer": {"@id": "ex:employer", "@type": "@id"},
            "addresses": {"@id": "ex:address", "@type": "@id"},
            "knows": {"@id": "ex:knows", "@type": "@id"},
            "best_friend": {"@id": "ex:bestFriend", "@type": "@id"},
        }


# 2. Register a backend so IRIs can be resolved


def setup_backend() -> SimpleDictDocumentStore:
    store = SimpleDictDocumentStore()
    store.store_json_dicts(
        {
            "ex:acme": {"id": "ex:acme", "name": "ACME Corp"},
            "ex:home": {"id": "ex:home", "city": "Berlin"},
            "ex:bob": {"id": "ex:bob", "name": "Bob"},
            "ex:carol": {"id": "ex:carol", "name": "Carol"},
        }
    )
    # resolve every "ex:" IRI through this store
    set_resolver(SetResolverParam(iri="ex", resolver=store))
    return store


# 3. Use it


def main() -> None:
    setup_backend()

    # Build a Person. Links may be given as IRIs (resolved on demand) or as
    # already-constructed objects - mixed freely.
    alice = Person(
        id="ex:alice",
        name="Alice",
        employer="ex:acme",  # by IRI
        addresses=["ex:home"],  # list of IRIs
        knows=["ex:bob", "ex:carol"],  # list of IRIs
        best_friend=Person(id="ex:bob", name="Bob"),  # by object
    )

    print("== transparent access returns REAL objects ==")
    # employer is lazily resolved through the backend on first access
    print("employer:", alice.employer.name)  # -> ACME Corp
    print(
        "isinstance(employer, Organization):", isinstance(alice.employer, Organization)
    )
    print("first address city:", alice.addresses[0].city)  # -> Berlin
    print(
        "knows[0]:",
        alice.knows[0].name,
        "| is Person:",
        isinstance(alice.knows[0], Person),
    )
    print("best_friend:", alice.best_friend.name)

    print("\n== inspect references WITHOUT resolving (explicit handle) ==")
    print("knows IRIs:", Person.knows.iris(alice))  # ['ex:bob', 'ex:carol']
    print("employer IRI:", Person.employer.iris(alice))  # 'ex:acme'

    print("\n== serialise: links collapse back to IRIs ==")
    print("JSON:", alice.model_dump(exclude_none=True))
    print("JSON-LD:", alice.to_jsonld())

    print("\n== mutate ==")
    alice.knows = ["ex:carol"]  # assignment coerces to a link
    print("knows after reassign:", [p.name for p in alice.knows])


if __name__ == "__main__":
    main()
