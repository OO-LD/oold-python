"""Parity between the shipped v1 LinkedBaseModel and the v1 descriptor binding.

The generated packages emit a v1 variant and the production entity models are
v1, declaring links with the bare keyword form ``Field(None, range="T")``, so v1
parity is a release blocker rather than a nice-to-have. Mirrors
``test_compat_parity.py``, which does the same for v2.
"""

import pytest
from pydantic.v1 import Field

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import SetResolverParam, set_resolver
from oold.model.v1 import LinkedBaseModel
from oold.model.v1._descriptor import AutoLinkedModelV1


def build(base, tag):
    """A model declared the way the v1 code generator emits it."""

    class T(base):
        id: str
        label: str | None = None
        type: str | None = f"ex:{tag}T"

    class M(base):
        id: str
        title: str | None = None
        type: str | None = f"ex:{tag}M"
        links: list[T] | None = Field(None, range="T")
        one: T | None = Field(None, range="T")

    return T, M


@pytest.fixture(scope="module", autouse=True)
def store():
    s = SimpleDictDocumentStore()
    for tag in ("SV", "AV"):
        s.store_json_dicts({
            f"ex:{tag}1": {"id": f"ex:{tag}1", "label": "one", "type": f"ex:{tag}T"},
            f"ex:{tag}2": {"id": f"ex:{tag}2", "label": "two", "type": f"ex:{tag}T"},
        })
    set_resolver(SetResolverParam(iri="ex", resolver=s))
    return s


def both():
    return [(tag, *build(base, tag)) for base, tag in ((LinkedBaseModel, "SV"), (AutoLinkedModelV1, "AV"))]


def collect(fn):
    """Run fn against both bindings, tag-normalised so results compare literally."""
    return [str(fn(tag, T, M)).replace(tag, "#") for tag, T, M in both()]


def test_bare_range_kwarg_is_detected():
    def probe(tag, T, M):
        m = M(id="ex:m", links=[f"ex:{tag}1"], one=f"ex:{tag}1")
        return type(m.links[0]).__name__, m.links[0].label, m.one.label

    shipped, auto = collect(probe)
    assert shipped == auto


def test_get_iri_ref_shapes_match():
    def probe(tag, T, M):
        m = M(id="ex:m", title="x", links=[f"ex:{tag}1", f"ex:{tag}2"], one=f"ex:{tag}1")
        return (
            m.get_iri_ref("links"),
            m.get_iri_ref("one"),
            m.get_iri_ref("title"),
        )

    shipped, auto = collect(probe)
    assert shipped == auto


def test_iris_read_and_write():
    def probe(tag, T, M):
        m = M(id="ex:m", links=[f"ex:{tag}1"])
        read = sorted(m.__iris__)
        m2 = M(id="ex:m2")
        m2.__iris__ = {"one": f"ex:{tag}2"}
        return read, m2.get_iri_ref("one"), m2.one.label

    shipped, auto = collect(probe)
    assert shipped == auto


def test_dict_and_to_json_match():
    def probe(tag, T, M):
        m = M(id="ex:m", title="x", links=[f"ex:{tag}1", f"ex:{tag}2"], one=f"ex:{tag}1")
        return m.dict(exclude_none=True), m.to_json()

    shipped, auto = collect(probe)
    assert shipped == auto


def test_raw_dict_lists_every_field():
    def probe(tag, T, M):
        m = M(id="ex:m", title="x", one=f"ex:{tag}1")
        raw = m._raw_dict()
        return sorted(raw), raw["one"], raw["links"]

    shipped, auto = collect(probe)
    assert shipped == auto


def test_api_surface_present():
    required = [
        "get_iri_ref",
        "get_raw",
        "to_json",
        "from_json",
        "to_jsonld",
        "from_jsonld",
        "cast",
        "cast_none_to_default",
        "get_cls_iri",
        "dict",
        "json",
    ]
    missing = [a for a in required if not hasattr(AutoLinkedModelV1, a)]
    assert missing == [], f"missing downstream API: {missing}"
