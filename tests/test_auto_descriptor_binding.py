"""Tests for the auto-installed descriptor binding.

Covers the recommended variant: link descriptors installed from annotations, so
the declaration syntax is unchanged. See docs/design/graph-object-binding.md.
"""

import subprocess
import sys

import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.experimental.auto_descriptor_binding import (
    AutoLinkedModel,
    Link,
    LinkList,
    OoldExtra,
    OoldField,
)

CALLS = []


class CountingStore(SimpleDictDocumentStore):
    def resolve_iris(self, iris):
        CALLS.append(list(iris))
        return super().resolve_iris(iris)


class Org(AutoLinkedModel):
    id: str
    name: str | None = None
    type: str | None = "ex:Org"


class Person(AutoLinkedModel):
    id: str
    name: str | None = None
    type: str | None = "ex:Person"
    knows: list["Person"] | None = OoldField(default=None, range="Person")
    employer = Link(Org)
    friends = LinkList["Person"]()


class Employee(Person):
    type: str | None = "ex:Employee"


Person.model_rebuild()


@pytest.fixture()
def store():
    CALLS.clear()
    s = CountingStore()
    s.store_json_dicts({
        "ex:p2": {"id": "ex:p2", "name": "Bob", "type": "ex:Person"},
        "ex:p3": {"id": "ex:p3", "name": "Carol", "type": "ex:Person"},
        "ex:e1": {"id": "ex:e1", "name": "Dave", "type": "ex:Employee"},
        "ex:acme": {"id": "ex:acme", "name": "ACME", "type": "ex:Org"},
    })
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def test_oold_field_without_arguments(store):
    """OoldField() with no args: the target is inferred from the annotation."""

    class Team(AutoLinkedModel):
        id: str
        type: str | None = "ex:Team"
        members: list[Org] | None = OoldField()

    Team.model_rebuild()
    t = Team(id="ex:t1", members=["ex:acme"])
    assert isinstance(t.members[0], Org) and t.members[0].name == "ACME"
    assert t.model_dump(exclude_none=True)["members"] == ["ex:acme"]


def test_implicit_and_explicit_forms_coexist(store):
    p = Person(id="ex:p1", name="Alice", knows=["ex:p2"], employer="ex:acme", friends=["ex:p3"])
    assert set(Person.__link_fields__) == {"knows", "employer", "friends"}
    assert isinstance(p.knows[0], Person) and p.knows[0].name == "Bob"
    assert isinstance(p.employer, Org) and p.employer.name == "ACME"
    assert isinstance(p.friends[0], Person) and p.friends[0].name == "Carol"


def test_explicit_descriptors_are_not_pydantic_fields():
    assert set(Person.model_fields) == {"id", "name", "type", "knows"}


def test_lazy_and_batched(store):
    p = Person(id="ex:p1", knows=["ex:p2", "ex:p3"])
    assert p.link_iris("knows") == ["ex:p2", "ex:p3"]
    assert CALLS == []  # nothing resolved yet
    assert [x.name for x in p.knows] == ["Bob", "Carol"]
    assert CALLS == [["ex:p2", "ex:p3"]]  # one batched call


def test_cached_read_uses_instance_dict(store):
    p = Person(id="ex:p1", knows=["ex:p2"])
    _ = p.knows
    n = len(CALLS)
    _ = p.knows
    assert len(CALLS) == n
    # the cache lives in the instance __dict__, shadowing the descriptor
    assert "knows" in p.__dict__


def test_mutation_invalidates_cache(store):
    p = Person(id="ex:p1", knows=["ex:p2"])
    assert p.knows[0].name == "Bob"
    p.knows = ["ex:p3"]
    assert p.knows[0].name == "Carol"
    assert p.link_iris("knows") == ["ex:p3"]


def test_polymorphic_resolution(store):
    p = Person(id="ex:p1", knows=["ex:e1"])
    assert isinstance(p.knows[0], Employee)  # subclass, not the declared target


def test_linked_object_is_validated():
    with pytest.raises(Exception):
        Person(id="ex:p1", knows=[{"name": "no id"}])  # 'id' is required


def test_list_operations(store):
    p = Person(id="ex:p1", knows=["ex:p2", "ex:p3"])
    assert p.knows["ex:p3"].name == "Carol"
    assert [x.id for x in p.knows[Person.name == "Bob"]] == ["ex:p2"]
    assert list(p.knows.name) == ["Bob", "Carol"]


def test_serialisation_to_iris(store):
    p = Person(id="ex:p1", name="Alice", knows=["ex:p2"], employer="ex:acme")
    d = p.model_dump(exclude_none=True)
    assert d["knows"] == ["ex:p2"]
    assert d["employer"] == "ex:acme"
    assert d["name"] == "Alice"


def test_query_dsl(store):
    cond = Person.name == "John"
    assert cond.field == "name" and cond.value == "John"
    assert Person[cond] is not None
    assert Person["ex:p1"] is not None
    assert (Employee.name == "x").field == "name"  # inherited field
    assert (Person.employer == "ex:acme").field == "employer"  # link descriptor


def test_typed_extras_validate():
    with pytest.raises(Exception):
        OoldExtra(range="")
    extra = OoldExtra(range="Person", required_iri=True)
    assert extra["x-oold-range"] == "Person"
    assert extra.range == "Person" and extra.required_iri is True


def test_extras_reach_the_json_schema():
    prop = Person.model_json_schema()["$defs"]["Person"]["properties"]["knows"]
    assert prop["x-oold-range"] == "Person"


def test_does_not_monkeypatch_fieldinfo():
    code = "import pydantic.fields as pf;import oold.experimental.auto_descriptor_binding;print(pf.FieldInfo.__name__)"
    res = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "FieldInfo"
