"""Acceptance tests for the experimental ``Ref[T]`` binding prototype.

Validates the binding recommendation in
``docs/design/graph-object-binding.md``:

1. construct a linked object by value and by IRI,
2. lazily resolve an IRI reference through the existing backend layer,
3. round-trip serialise references back to IRIs in JSON and JSON-LD,
4. match the shipped ``LinkedBaseModel`` reference-replacement output,
5. prove the prototype does not trigger the process-wide ``FieldInfo``
   monkeypatch that ``oold.model`` performs,
6. micro-benchmark plain attribute access against the shipped model.
"""

import subprocess
import sys
import time

import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.experimental.ref_binding import Bar, Foo, Person, Ref


@pytest.fixture()
def store():
    """A backend with ex:b/ex:b1/ex:b2 registered under the ``ex`` prefix."""
    s = SimpleDictDocumentStore()
    s.store_json_dicts(
        {
            "ex:b": {"id": "ex:b", "prop1": "resolved-b"},
            "ex:b1": {"id": "ex:b1", "prop1": "resolved-b1"},
            "ex:b2": {"id": "ex:b2", "prop1": "resolved-b2"},
        }
    )
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def test_build_by_object():
    f = Foo(id="ex:f", literal="test1", b=Bar(id="ex:b", prop1="inline"))
    assert isinstance(f.b, Ref)
    # inline object is available without any backend
    assert f.b.resolved is True
    assert f.b.prop1 == "inline"
    assert f.b.id == "ex:b"


def test_build_by_iri_is_lazy(store):
    f = Foo(id="ex:f", b="ex:b")
    # not resolved until first access
    assert f.b.resolved is False
    assert f.b.iri == "ex:b"
    # first access triggers backend resolution and caches it
    assert f.b.prop1 == "resolved-b"
    assert f.b.resolved is True


def test_list_refs_build_and_resolve(store):
    f = Foo(id="ex:f", b2=["ex:b1", "ex:b2"])
    assert [r.iri for r in f.b2] == ["ex:b1", "ex:b2"]
    assert [r.prop1 for r in f.b2] == ["resolved-b1", "resolved-b2"]


def test_transparent_linked_field_is_lazy_and_typed(store):
    """The transparent form: field declared as list[Person] (via Linked).

    Statically ``person.knows[0]`` is ``Person`` (autocomplete works; verified
    separately with pyright). At runtime each item is a lazy ``Ref`` that
    resolves through the backend and serialises back to an IRI.
    """
    store.store_json_dicts(
        {
            "ex:p2": {"id": "ex:p2", "name": "Bob"},
            "ex:p3": {"id": "ex:p3", "name": "Carol"},
        }
    )
    p = Person(id="ex:p1", name="Alice", knows=["ex:p2", "ex:p3"])

    # runtime value is a lazy Ref, unresolved until accessed
    assert isinstance(p.knows[0], Ref)
    assert p.knows[0].resolved is False
    # transparent access resolves through the backend and reads a Person field
    assert p.knows[0].name == "Bob"
    assert p.knows[1].name == "Carol"
    # references serialise back to IRIs
    assert p.model_dump(exclude_none=True)["knows"] == ["ex:p2", "ex:p3"]


def test_transparent_linked_build_by_object():
    p = Person(id="ex:p1", knows=[Person(id="ex:p2", name="Bob")])
    assert p.knows[0].resolved is True
    assert p.knows[0].name == "Bob"
    assert p.model_dump(exclude_none=True)["knows"] == ["ex:p2"]


def test_json_serialises_refs_to_iris():
    f = Foo(
        id="ex:f",
        literal="test1",
        b=Bar(id="ex:b", prop1="inline"),
        b2=[Bar(id="ex:b1"), Bar(id="ex:b2")],
    )
    dump = f.to_json()
    assert dump["b"] == "ex:b"
    assert dump["b2"] == ["ex:b1", "ex:b2"]
    # plain field untouched
    assert dump["literal"] == "test1"


def test_jsonld_refs_are_id_nodes(store):
    pytest.importorskip("pyld")
    from pyld import jsonld

    f = Foo(id="ex:f", b="ex:b")
    doc = f.to_jsonld()
    assert doc["b"] == "ex:b"  # compact form still an IRI, not an inline object

    expanded = jsonld.expand(doc)
    node = expanded[0]
    # b expands to an @id reference (a linked node), not a literal / nested obj
    b_values = node["https://example.org/hasB"]
    assert b_values == [{"@id": "https://example.org/b"}]
    # expansion resolves the compact id ex:f to its full IRI
    assert node["@id"] == "https://example.org/f"


def test_equivalence_with_linked_base_model(store):
    # Importing oold.model applies the FieldInfo monkeypatch to THIS process;
    # that is fine here - the isolation guarantee is checked in a subprocess
    # (test_poc_does_not_monkeypatch_fieldinfo).
    from typing import List, Optional

    from pydantic import Field as PydField

    from oold.model import LinkedBaseModel

    class LBar(LinkedBaseModel):
        id: str
        prop1: Optional[str] = None

    class LFoo(LinkedBaseModel):
        id: str
        literal: Optional[str] = None
        b: Optional[LBar] = PydField(default=None, json_schema_extra={"range": "LBar"})
        b2: Optional[List[LBar]] = PydField(
            default=None, json_schema_extra={"range": "LBar"}
        )

    shipped = LFoo(
        id="ex:f",
        literal="test1",
        b=LBar(id="ex:b", prop1="inline"),
        b2=[LBar(id="ex:b1"), LBar(id="ex:b2")],
    ).to_json()
    proto = Foo(
        id="ex:f",
        literal="test1",
        b=Bar(id="ex:b", prop1="inline"),
        b2=[Bar(id="ex:b1"), Bar(id="ex:b2")],
    ).to_json()

    # The prototype reproduces the shipped model's reference-replacement:
    # object references collapse to IRIs, identically.
    assert proto["b"] == shipped["b"] == "ex:b"
    assert proto["b2"] == shipped["b2"] == ["ex:b1", "ex:b2"]


def test_poc_does_not_monkeypatch_fieldinfo():
    """Importing the prototype must not patch pydantic.fields.FieldInfo."""
    code = (
        "import pydantic.fields as pf;"
        "import oold.experimental.ref_binding;"  # noqa: F401
        "print(pf.FieldInfo.__name__)"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert (
        res.stdout.strip() == "FieldInfo"
    ), f"prototype patched FieldInfo -> {res.stdout.strip()!r}\n{res.stderr}"


def test_attribute_access_benchmark(capsys):
    """Plain-field access on the prototype vs the shipped LinkedBaseModel.

    The shipped model overrides ``__getattribute__`` on every instance, so even
    non-reference fields pay for the binding. The prototype leaves plain fields
    to native pydantic. We record the ratio; the only hard assertion is a very
    loose sanity bound so the test is not flaky.
    """
    from typing import Optional

    from oold.model import LinkedBaseModel

    class LPlain(LinkedBaseModel):
        id: str
        literal: Optional[str] = None

    proto = Foo(id="ex:f", literal="x")
    shipped = LPlain(id="ex:f", literal="x")

    n = 200_000

    t0 = time.perf_counter()
    for _ in range(n):
        proto.literal  # noqa: B018
    proto_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(n):
        shipped.literal  # noqa: B018
    shipped_t = time.perf_counter() - t0

    with capsys.disabled():
        print(
            f"\n[attr-access {n:,}x] prototype={proto_t*1e3:.1f}ms "
            f"shipped={shipped_t*1e3:.1f}ms "
            f"ratio(shipped/proto)={shipped_t / proto_t:.2f}x"
        )
    # sanity only: the prototype must not be pathologically slower
    assert proto_t < shipped_t * 10
