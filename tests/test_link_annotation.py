"""``Link[T]`` / ``LinkList[T]`` used as the whole annotation.

The static half of this contract lives in ``tests/typing/links.py``; here is the
runtime half. Two things to hold down:

* the annotation form must be indistinguishable from the plain spelling - same
  schema, same resolution, same serialisation. It only adds what a checker sees;
* optionality is **declared**. ``Link[T]`` promises a ``T``, so the binding keeps
  that promise rather than handing back a ``None`` the type denies;
  ``Link[T | None]`` says absence is data and returns ``None``.
"""

import pytest
from pydantic import Field

from oold.backend import interface
from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model._descriptor import (
    Link,
    LinkedBaseModel,
    LinkList,
    LinkNotResolved,
    OoldField,
)


class Org(LinkedBaseModel):
    id: str
    name: str | None = None
    type: str | None = "annot:Organization"


class Person(LinkedBaseModel):
    id: str
    name: str | None = None
    type: str | None = "annot:Person"
    knows: LinkList["Person | None"] = OoldField()
    employer: Link["Org | None"] = OoldField()
    mixed: LinkList["Person | Org | None"] = OoldField()


class Employee(LinkedBaseModel):
    """Every employee has an employer - declared, and enforced."""

    id: str
    type: str | None = "annot:Employee"
    employer: Link[Org] = OoldField()


class Plain(LinkedBaseModel):
    id: str
    type: str | None = "annot:Plain"
    knows: list["Person"] | None = Field(None, json_schema_extra={"range": "Person"})


Person.model_rebuild()
Employee.model_rebuild()
Plain.model_rebuild()


@pytest.fixture
def store():
    # the resolver registry is process-wide, and an unregistered prefix falls
    # back to whatever else is in it - so leaking one breaks unrelated modules
    saved = dict(interface._resolvers)
    store = SimpleDictDocumentStore()
    store.store_json_dicts({
        "annot:bob": {"id": "annot:bob", "name": "Bob", "type": "annot:Person"},
        "annot:acme": {"id": "annot:acme", "name": "ACME", "type": "annot:Organization"},
    })
    set_resolver(SetResolverParam(iri="annot", resolver=store))
    yield store
    interface._resolvers.clear()
    interface._resolvers.update(saved)


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
    assert plain["anyOf"][0]["items"] == {"$ref": "#/$defs/Person"}
    # the annotated form carries the None arm it declares
    assert {"$ref": "#/$defs/Person"} in annotated["items"]["anyOf"]


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

    class Explicit(LinkedBaseModel):
        id: str
        type: str | None = "annot:Explicit"
        employer = Link(Org)
        knows = LinkList("Person")

    e = Explicit(id="annot:e", employer="annot:acme")
    assert isinstance(e.employer, Org)
    assert e.employer.name == "ACME"


# -- optionality is declared -------------------------------------------------


def test_optional_link_unset_reads_as_none(store):
    assert Person(id="annot:a").employer is None


def test_optional_link_keeps_the_slot_of_an_unresolvable_reference(store):
    """The list stays aligned with the stored references."""
    p = Person(id="annot:a", knows=["annot:bob", "annot:nobody"])
    assert len(p.knows) == 2
    assert p.knows[1] is None
    assert p.link_iris("knows") == ["annot:bob", "annot:nobody"]


def test_mandatory_link_unset_raises_on_access_not_on_construction(store):
    """Partial graph data must still load; the promise is about reading."""
    e = Employee(id="annot:e")  # builds fine
    with pytest.raises(LinkNotResolved, match="not set"):
        _ = e.employer


def test_a_whole_chain_needs_one_except_not_a_guard_per_hop(store):
    """The point of declaring a link mandatory."""

    class Node(LinkedBaseModel):
        id: str
        type: str | None = "annot:Node"
        parent: Link["Node"] = OoldField()

    Node.model_rebuild()
    leaf = Node(id="annot:leaf", parent={"id": "annot:mid"})
    with pytest.raises(LinkNotResolved):
        _ = leaf.parent.parent.parent


def test_mandatory_link_resolves(store):
    e = Employee(id="annot:e", employer="annot:acme")
    assert isinstance(e.employer, Org)
    assert e.employer.name == "ACME"


def test_mandatory_link_raises_when_the_backend_has_no_such_entity(store):
    """Only detectable on access - and None would deny the declared type."""
    e = Employee(id="annot:e", employer="annot:ghost")
    with pytest.raises(LinkNotResolved, match="declared mandatory"):
        _ = e.employer


def test_backend_errors_are_not_mistaken_for_absence(store):
    """A transport failure is not 'has no employer' - it propagates."""

    class Boom(type(store)):
        def resolve_iris(self, iris):
            raise ConnectionError("backend unreachable")

    set_resolver(SetResolverParam(iri="annot", resolver=Boom()))
    e = Employee(id="annot:e", employer="annot:acme")
    with pytest.raises(ConnectionError):
        _ = e.employer


def test_union_target_resolves_on_a_jsonld_backend():
    """The case the broad fallback hid.

    A union target is not a class, so it cannot be a ``model_cls``. Passing it
    made ``ResolveParam`` validation fail, which dropped into ``_batch_resolve``'s
    ``except Exception`` and rebuilt the *raw* document - fine for a JSON store,
    broken for every JSON-LD one, which is where this runs.
    """
    from pydantic import ConfigDict
    from rdflib import Graph

    from oold.backend.sparql import LocalSparqlBackend

    UN = "https://union.example/"
    context = {
        "@context": {"id": "@id", "type": "@type", "name": UN + "name"},
        "iri": UN + "Base",
    }

    class UBase(LinkedBaseModel):
        model_config = ConfigDict(json_schema_extra=context)
        id: str
        name: str | None = None

        def get_iri(self):
            return self.id

    class UPerson(UBase):
        model_config = ConfigDict(json_schema_extra={**context, "iri": UN + "Person"})
        type: str | None = UN + "Person"

    class UOrg(UBase):
        model_config = ConfigDict(json_schema_extra={**context, "iri": UN + "Org"})
        type: str | None = UN + "Org"

    class UHolder(UBase):
        model_config = ConfigDict(json_schema_extra={**context, "iri": UN + "Holder"})
        type: str | None = UN + "Holder"
        mixed: LinkList["UPerson | UOrg | None"] = OoldField()

    UHolder.model_rebuild()

    saved = dict(interface._resolvers)
    try:
        store = LocalSparqlBackend(graph=Graph())
        store.store_jsonld_dicts({
            UN + "bob": UPerson(id=UN + "bob", name="Bob").to_jsonld(),
            UN + "acme": UOrg(id=UN + "acme", name="ACME").to_jsonld(),
        })
        set_resolver(SetResolverParam(iri="https", resolver=store))
        h = UHolder(id=UN + "h", mixed=[UN + "bob", UN + "acme"])
        assert [type(v).__name__ for v in h.mixed] == ["UPerson", "UOrg"]
        assert [v.name for v in h.mixed] == ["Bob", "ACME"]
    finally:
        interface._resolvers.clear()
        interface._resolvers.update(saved)


def test_a_malformed_document_reports_its_own_error(store):
    """The fallback used to swallow it and mis-construct against the target."""

    class Broken(type(store)):
        def resolve_iris(self, iris):
            return {i: {"id": i, "type": "annot:Person", "name": {"not": "a string"}} for i in iris}

    set_resolver(SetResolverParam(iri="annot", resolver=Broken()))
    p = Person(id="annot:a", knows=["annot:x"])
    with pytest.raises(Exception) as excinfo:
        _ = p.knows
    # the model's own validation error, not a downstream TypeError from
    # re-constructing an expanded document against the declared target
    assert "name" in str(excinfo.value)


def test_mutating_a_link_list_never_discards_an_unresolved_reference(store):
    """_sync rebuilt storage from the resolved values, so a slot that could not
    be resolved was deleted - the list shrank and the IRI was lost."""
    p = Person(id="annot:a", knows=["annot:bob", "annot:nobody"])
    assert p.knows[1] is None
    p.knows.append(Person(id="annot:c"))
    assert p.link_iris("knows") == ["annot:bob", "annot:nobody", "annot:c"]


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda lst: lst.__setitem__(0, Person(id="annot:z")), ["annot:z", "annot:bob"]),
        (lambda lst: lst.pop(), ["annot:acme"]),
        (lambda lst: lst.insert(0, Person(id="annot:z")), ["annot:z", "annot:acme", "annot:bob"]),
        (lambda lst: lst.clear(), []),
        (lambda lst: lst.reverse(), ["annot:bob", "annot:acme"]),
        (lambda lst: lst.__delitem__(0), ["annot:bob"]),
        (lambda lst: lst.__iadd__([Person(id="annot:z")]), ["annot:acme", "annot:bob", "annot:z"]),
    ],
)
def test_every_list_mutation_reaches_storage(store, mutate, expected):
    """Only append/remove/extend synced; the rest changed the visible list while
    storage kept the old references."""
    p = Person(id="annot:a", mixed=["annot:acme", "annot:bob"])
    values = p.mixed
    mutate(values)
    assert p.link_iris("mixed") == expected
