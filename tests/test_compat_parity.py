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
from oold.model import _LinkedBaseModelLegacy as LegacyLinkedBaseModel
from oold.model._descriptor import LinkedBaseModel


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
    return [(tag, *build(base, tag)) for base, tag in ((LegacyLinkedBaseModel, "S"), (LinkedBaseModel, "A"))]


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
    missing = [a for a in required if not hasattr(LinkedBaseModel, a)]
    assert missing == [], f"missing downstream API: {missing}"


# -- regressions found by review (these paths were not covered) --------------


def test_controller_to_json_keeps_the_data_fields():
    """A controller whose only model base is the binding's own base class.

    Downstream controllers mix BaseController with a concrete model, which hid
    this: the descriptor binding adds LinkedApiMixin to the MRO, the data-model
    detection accepted it as the data model, and to_json() then intersected the
    payload against an empty field set.
    """
    from oold.model import BaseController

    dumped = []
    for base, tag in ((LegacyLinkedBaseModel, "SC"), (LinkedBaseModel, "AC")):

        class C(BaseController, base):
            id: str
            type: str | None = f"ex:{tag}"
            note: str | None = "n"

        dumped.append(sorted(C(id=f"ex:{tag.lower()}").to_json()))
    assert dumped[0] == dumped[1], dumped
    assert "note" in dumped[1]


def test_field_proxy_truthiness_and_default_forwarding_match():
    """Downstream writes `if Model.field:` and `Model.field.startswith(...)`."""
    seen = []
    for base, tag in ((LegacyLinkedBaseModel, "SP"), (LinkedBaseModel, "AP")):

        class B(base):
            id: str
            type: str | None = f"ex:{tag}"
            empty: str | None = None
            filled: str | None = "default-name"

        seen.append((bool(B.empty), bool(B.filled), B.filled.upper()))
    assert seen[0] == seen[1], seen


def test_iris_assignment_replaces_rather_than_merges():
    for tag, _T, M in both():
        m = M(id=f"ex:{tag}m", one=f"ex:{tag}1")
        assert m.__iris__, tag
        m.__iris__ = {}
        assert m.__iris__ == {}, tag


def test_get_raw_does_not_invent_a_none_element():
    for tag, _T, M in both():
        m = M(id=f"ex:{tag}m", links=[f"ex:{tag}-unresolved"])
        assert m.get_raw("links") is None, tag


def test_required_iri_is_enforced():
    for base, tag in ((LegacyLinkedBaseModel, "SR"), (LinkedBaseModel, "AR")):
        target, _model = build(base, tag)

        class R(base):
            id: str
            type: str | None = f"ex:{tag}"
            one: target | None = Field(None, json_schema_extra={"range": f"ex:{tag}T", "x-oold-required-iri": True})

        R.model_rebuild()
        with pytest.raises(ValueError, match="required but not set"):
            R(id=f"ex:{tag.lower()}")


def test_unset_and_empty_links_serialise_the_same_way():
    """`links=[]` is a different statement from unset, and both must survive."""
    unset, empty = [], []
    for tag, _T, M in both():
        unset.append(normalised(M(id=f"ex:{tag}m").model_dump(), tag))
        empty.append(normalised(M(id=f"ex:{tag}m", links=[]).model_dump()["links"], tag))
    assert unset[0] == unset[1], unset
    assert empty[0] == empty[1], empty


def test_inline_object_without_an_iri_is_not_dropped():
    """cast() is built on _raw_dict, so losing it there loses it everywhere."""
    seen = []
    for base, tag in ((LegacyLinkedBaseModel, "SI"), (LinkedBaseModel, "AI")):

        class T(base):
            id: str | None = None  # a blank node: inline, never referenced
            label: str | None = None
            type: str | None = f"ex:{tag}T"

        class M(base):
            id: str
            type: str | None = f"ex:{tag}M"
            one: T | None = Field(None, json_schema_extra={"range": f"ex:{tag}T"})

        M.model_rebuild()
        seen.append(normalised(M(id=f"ex:{tag}m", one=T(label="anon"))._raw_dict()["one"], tag))
    assert seen[0] == seen[1], seen
    assert "anon" in str(seen[1])


def test_iris_assignment_keeps_inline_objects_and_foreign_keys():
    """Replacing the side-dict must not destroy values it never held.

    The side-dict held IRIs only, so clearing it never removed an inline object,
    and a key that is not a link field was remembered rather than written over
    the model field of that name.
    """
    inline, foreign = [], []
    for tag, T, M in both():
        a = M(id=f"ex:{tag}m", one=T(id=f"ex:{tag}inline", label="inline"))
        a.__iris__ = {"links": [f"ex:{tag}1"]}
        one = a.one
        inline.append(one.label if one is not None else None)

        b = M(id=f"ex:{tag}m", title="hello")
        b.__iris__ = {"title": f"ex:{tag}notalink"}
        foreign.append((b.title, normalised(b.get_iri_ref("title"), tag)))
    assert inline[0] == inline[1] == "inline"
    assert foreign[0] == foreign[1], foreign
