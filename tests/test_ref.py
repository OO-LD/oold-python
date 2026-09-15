"""Unit tests for :class:`oold.model._ref.Ref`.

``Ref`` is the value the descriptor binding stores for a link: it holds either
an unresolved IRI or a resolved object. That indirection is what lets a link be
inspected without resolving it, resolved in batches, and serialised back to an
IRI.
"""

import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model._ref import OoldModel, Ref

RESOLVE_CALLS = []


class CountingStore(SimpleDictDocumentStore):
    def resolve_iris(self, iris):
        RESOLVE_CALLS.append(list(iris))
        return super().resolve_iris(iris)


class Target(OoldModel):
    id: str
    label: str | None = None


@pytest.fixture()
def store():
    RESOLVE_CALLS.clear()
    s = CountingStore()
    s.store_json_dicts({"ex:t1": {"id": "ex:t1", "label": "one"}})
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def test_holds_an_unresolved_iri(store):
    ref = Ref(iri="ex:t1", target=Target)
    assert ref.iri == "ex:t1"
    assert ref.resolved is False
    assert RESOLVE_CALLS == []  # inspecting must not resolve


def test_resolves_on_demand_and_caches(store):
    ref = Ref(iri="ex:t1", target=Target)
    obj = ref.resolve()
    assert isinstance(obj, Target) and obj.label == "one"
    assert ref.resolved is True
    ref.resolve()
    assert len(RESOLVE_CALLS) == 1  # second call served from the cache


def test_holds_an_object_and_derives_its_iri():
    ref = Ref(obj=Target(id="ex:t9", label="nine"))
    assert ref.resolved is True
    assert ref.iri == "ex:t9"  # taken from the object


def test_attribute_access_delegates(store):
    ref = Ref(iri="ex:t1", target=Target)
    assert ref.label == "one"  # resolves, then reads through


def test_equality_and_hash_are_by_iri():
    assert Ref(iri="ex:t1") == Ref(iri="ex:t1")
    assert Ref(iri="ex:t1") != Ref(iri="ex:t2")
    assert len({Ref(iri="ex:t1"), Ref(iri="ex:t1")}) == 1


def test_missing_target_raises(store):
    with pytest.raises(KeyError):
        Ref(iri="ex:absent", target=Target).resolve()


def test_aresolve_is_available():
    """Async resolution exists as a handle; the in-repo backends are sync."""
    assert callable(Ref(iri="ex:t1").aresolve)
