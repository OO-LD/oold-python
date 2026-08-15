"""Acceptance tests for the transparent descriptor-based binding prototype.

This is the recommended binding: plain access returns the REAL resolved object
(``isinstance`` holds), resolution is lazy and batched, only link fields are
taxed, and there is no metaclass / no ``FieldInfo`` monkeypatch. See
``docs/design/graph-object-binding.md`` and ``descriptor_binding.py``.
"""

import asyncio
import subprocess
import sys
import time

import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.experimental.descriptor_binding import Person

RESOLVE_CALLS = []


class CountingStore(SimpleDictDocumentStore):
    def resolve_iris(self, iris):
        RESOLVE_CALLS.append(list(iris))
        return super().resolve_iris(iris)


@pytest.fixture()
def store():
    RESOLVE_CALLS.clear()
    s = CountingStore()
    s.store_json_dicts(
        {
            "ex:p2": {"id": "ex:p2", "name": "Bob"},
            "ex:p3": {"id": "ex:p3", "name": "Carol"},
        }
    )
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def test_access_returns_real_object(store):
    """The core fix: p.knows[0] is a real Person, not a proxy."""
    p = Person(id="ex:p1", name="Alice", knows=["ex:p2"])
    item = p.knows[0]
    assert isinstance(item, Person)  # real object - not a Ref
    assert item.name == "Bob"
    # can be used anywhere a Person is expected
    assert type(item) is Person


def test_resolution_is_lazy_and_batched(store):
    p = Person(id="ex:p1", knows=["ex:p2", "ex:p3"])
    # inspecting IRIs must not resolve
    assert p.link_iris("knows") == ["ex:p2", "ex:p3"]
    assert RESOLVE_CALLS == []
    # accessing resolves ALL items in ONE backend call
    names = [x.name for x in p.knows]
    assert names == ["Bob", "Carol"]
    assert RESOLVE_CALLS == [["ex:p2", "ex:p3"]]


def test_resolution_is_cached(store):
    p = Person(id="ex:p1", knows=["ex:p2", "ex:p3"])
    _ = p.knows
    _ = p.knows  # second access
    assert len(RESOLVE_CALLS) == 1  # not re-resolved


def test_build_by_object_no_backend():
    p = Person(id="ex:p1", knows=[Person(id="ex:p2", name="Bob")])
    assert isinstance(p.knows[0], Person)
    assert p.knows[0].name == "Bob"
    assert p.link_iris("knows") == ["ex:p2"]


def test_single_link(store):
    p = Person(id="ex:p1", best_friend="ex:p2")
    assert p.link_iris("best_friend") == "ex:p2"
    assert isinstance(p.best_friend, Person)
    assert p.best_friend.name == "Bob"
    empty = Person(id="ex:p9")
    assert empty.best_friend is None


def test_mutation_via_setter(store):
    p = Person(id="ex:p1")
    p.knows = ["ex:p2"]  # assignment coerces to a link
    assert p.link_iris("knows") == ["ex:p2"]
    assert p.knows[0].name == "Bob"
    p.best_friend = Person(id="ex:p3", name="Carol")
    assert p.link_iris("best_friend") == "ex:p3"


def test_serialisation_to_iris(store):
    p = Person(
        id="ex:p1",
        name="Alice",
        knows=[Person(id="ex:p2"), Person(id="ex:p3")],
        best_friend="ex:p2",
    )
    dump = p.model_dump(exclude_none=True)
    assert dump["knows"] == ["ex:p2", "ex:p3"]
    assert dump["best_friend"] == "ex:p2"
    assert dump["name"] == "Alice"


def test_jsonld_refs_are_id_nodes(store):
    pytest.importorskip("pyld")
    from pyld import jsonld

    p = Person(id="ex:p1", knows=["ex:p2"])
    doc = p.to_jsonld()
    assert doc["knows"] == ["ex:p2"]
    expanded = jsonld.expand(doc)[0]
    assert expanded["https://example.org/knows"] == [{"@id": "https://example.org/p2"}]


def test_explicit_handles(store):
    p = Person(id="ex:p1", knows=["ex:p2", "ex:p3"])
    # raw IRIs and Ref handles without resolving
    assert Person.knows.iris(p) == ["ex:p2", "ex:p3"]
    assert [r.iri for r in Person.knows.refs(p)] == ["ex:p2", "ex:p3"]
    assert RESOLVE_CALLS == []
    # async resolution handle
    resolved = asyncio.run(Person.knows.aresolve(p))
    assert [x.name for x in resolved] == ["Bob", "Carol"]


def test_knows_is_not_a_pydantic_field():
    # link descriptors must not leak into the pydantic field set
    assert set(Person.model_fields) == {"id", "name"}


def test_no_getattribute_override():
    # the whole point: plain attribute access is native (no per-access tax)
    from oold.experimental.descriptor_binding import LinkedModel

    assert "__getattribute__" not in LinkedModel.__dict__


def test_does_not_monkeypatch_fieldinfo():
    code = (
        "import pydantic.fields as pf;"
        "import oold.experimental.descriptor_binding;"  # noqa: F401
        "print(pf.FieldInfo.__name__)"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "FieldInfo", res.stdout + res.stderr


def test_plain_field_access_benchmark(capsys):
    from typing import Optional

    from oold.model import LinkedBaseModel

    class LPlain(LinkedBaseModel):
        id: str
        literal: Optional[str] = None

    proto = Person(id="ex:p1", name="x")
    shipped = LPlain(id="ex:p1", literal="x")
    n = 200_000

    t0 = time.perf_counter()
    for _ in range(n):
        proto.name  # noqa: B018
    proto_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(n):
        shipped.literal  # noqa: B018
    shipped_t = time.perf_counter() - t0

    with capsys.disabled():
        print(
            f"\n[plain-access {n:,}x] descriptor-model={proto_t*1e3:.1f}ms "
            f"shipped={shipped_t*1e3:.1f}ms "
            f"ratio(shipped/proto)={shipped_t / proto_t:.2f}x"
        )
    assert proto_t < shipped_t * 10  # sanity only
