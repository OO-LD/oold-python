"""Parity between the shipped LinkedBaseModel and the descriptor binding.

The descriptor binding is only adoptable if downstream keeps working unchanged.
Downstream inherits its API from ``LinkedBaseModel`` via ``OswBaseModel``; the
members asserted here are the ones a scan of the generated ``opensemantic.*``
packages and the applications built on them found in active use. See
``docs/design/downstream-migration.md``.

Each behaviour is exercised on the *same* generated-style model declared on both
bases, and the results compared.
"""

import pytest
from pydantic import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model import LinkedBaseModel
from oold.model._descriptor import AutoLinkedModel


def build(base, tag):
    """A model declared exactly the way the code generator emits it."""

    class T(base):
        id: str
        label: str | None = None
        type: str | None = f"ex:{tag}T"

    class M(base):
        id: str
        title: str | None = None
        type: str | None = f"ex:{tag}M"
        links: list[T] | None = Field(None, json_schema_extra={"range": "T"})
        one: T | None = Field(None, json_schema_extra={"range": "T"})

    return T, M


@pytest.fixture(scope="module", autouse=True)
def store():
    s = SimpleDictDocumentStore()
    for tag in ("S", "A"):
        s.store_json_dicts({
            f"ex:{tag}1": {"id": f"ex:{tag}1", "label": "one", "type": f"ex:{tag}T"},
            f"ex:{tag}2": {"id": f"ex:{tag}2", "label": "two", "type": f"ex:{tag}T"},
        })
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def both():
    """Yield (tag, T, M) for the shipped and the descriptor binding."""
    return [(tag, *build(base, tag)) for base, tag in ((LinkedBaseModel, "S"), (AutoLinkedModel, "A"))]


def normalised(value, tag):
    """Strip the per-binding tag so results can be compared literally."""
    return str(value).replace(tag, "#")


def collect(fn):
    """Run fn against both bindings and return the tag-normalised results."""
    out = []
    for tag, T, M in both():
        out.append(normalised(fn(tag, T, M), tag))
    return out


def test_get_iri_ref_shapes_match():
    def probe(tag, T, M):
        m = M(id="ex:m", title="x", links=[f"ex:{tag}1", f"ex:{tag}2"], one=f"ex:{tag}1")
        return (
            m.get_iri_ref("links"),  # list of IRIs
            m.get_iri_ref("one"),  # single IRI
            m.get_iri_ref("title"),  # not a link -> None
        )

    shipped, auto = collect(probe)
    assert shipped == auto


def test_iris_read_matches():
    def probe(tag, T, M):
        m = M(id="ex:m", links=[f"ex:{tag}1"], one=f"ex:{tag}1")
        return sorted(m.__iris__), m.__iris__.get("one")

    shipped, auto = collect(probe)
    assert shipped == auto


def test_iris_write_is_honoured():
    """Pattern C: downstream assigns __iris__ directly to fabricate a link."""

    def probe(tag, T, M):
        m = M(id="ex:m2")
        m.__iris__ = {"one": f"ex:{tag}1"}
        return m.get_iri_ref("one"), type(m.one).__name__, m.one.label

    shipped, auto = collect(probe)
    assert shipped == auto


def test_to_json_matches():
    def probe(tag, T, M):
        m = M(id="ex:m", title="x", links=[f"ex:{tag}1", f"ex:{tag}2"], one=f"ex:{tag}1")
        return m.to_json()

    shipped, auto = collect(probe)
    assert shipped == auto


def test_links_resolve_to_real_objects():
    def probe(tag, T, M):
        m = M(id="ex:m", links=[f"ex:{tag}1", f"ex:{tag}2"])
        return [x.label for x in m.links], isinstance(m.links[0], T)

    shipped, auto = collect(probe)
    assert shipped == auto


def test_raw_dict_lists_every_field():
    """cast() is built on _raw_dict, so a missing key silently drops a field."""

    def probe(tag, T, M):
        m = M(id="ex:m", title="x", one=f"ex:{tag}1")
        raw = m._raw_dict()
        return sorted(raw), raw["one"], raw["links"]

    shipped, auto = collect(probe)
    assert shipped == auto


def test_cast_preserves_links():
    def probe(tag, T, M):
        m = M(id="ex:m", title="x", one=f"ex:{tag}1")
        other = M(m, title="y")  # construct from another instance
        return other.get_iri_ref("one"), other.title

    shipped, auto = collect(probe)
    assert shipped == auto


def test_api_surface_present():
    """Every member downstream inherits must exist on the new base."""
    required = [
        "get_iri_ref",
        "get_raw",
        "to_json",
        "from_json",
        "to_jsonld",
        "from_jsonld",
        "cast",
        "cast_none_to_default",
        "export_schema",
        "get_cls_iri",
        "store_jsonld",
    ]
    missing = [a for a in required if not hasattr(AutoLinkedModel, a)]
    assert missing == [], f"missing downstream API: {missing}"
