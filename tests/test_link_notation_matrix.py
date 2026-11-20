"""The notation table, row by row - issue #159.

One test per runtime column of the table in
``docs/how-to/object-graph-mapping.md``: *required* (construction outcome),
*unset read* and *in required[]*. The read-type columns are static and live in
``tests/typing/links.py``, checked by pyright and ty via ``test_typing.py``.

Each row is a parameter whose id is the spelling, so a missing row is visible
in the test names. Type IRIs are prefixed ``mx:`` to stay out of the
process-wide registry's way.
"""

from typing import Optional

import pytest
from pydantic import ConfigDict

# The descriptor binding directly, not the OOLD_DESCRIPTOR_BINDING-dependent
# name: the table is about the annotation form, which only this binding has.
from oold.model._descriptor import (
    Link,
    LinkedBaseModel,
    LinkList,
    LinkNotResolved,
    LinkNotSet,
    LinkUnresolvable,
    OoldField,
)


class Org(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/Org"})
    id: str
    type: str | None = "mx:Org"


# The classes are literal bodies, not type() calls: annotation capture differs
# between the two, and the table documents the form a user writes.


class M0(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M0"})
    id: str
    type: str | None = "mx:M0"
    f: Link[Org]


class M1(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M1"})
    id: str
    type: str | None = "mx:M1"
    f: Link[Org] = OoldField()


class M2(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M2"})
    id: str
    type: str | None = "mx:M2"
    f: Optional[Link[Org]] = None  # noqa: UP045 - the spelling under test


class M3(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M3"})
    id: str
    type: str | None = "mx:M3"
    f: Link[Org] | None = None


class M4(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M4"})
    id: str
    type: str | None = "mx:M4"
    f: Optional[Link[Org]] = OoldField()  # noqa: UP045 - the spelling under test


class M5(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M5"})
    id: str
    type: str | None = "mx:M5"
    f: Link[Org] = OoldField(required=False)


class M6(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M6"})
    id: str
    type: str | None = "mx:M6"
    f: LinkList[Org]


class M7(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M7"})
    id: str
    type: str | None = "mx:M7"
    f: Optional[LinkList[Org]] = None  # noqa: UP045 - the spelling under test


class M8(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M8"})
    id: str
    type: str | None = "mx:M8"
    f: LinkList[Org | None] = OoldField()


class M9(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M9"})
    id: str
    type: str | None = "mx:M9"
    f: LinkList[Org] = OoldField(required=False)


class M10(LinkedBaseModel):
    model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/M10"})
    id: str
    type: str | None = "mx:M10"
    f: Link[Org] = OoldField(default="mx:o1")


# spelling -> class and expected columns
ROWS = {
    "Link[Org]": {"cls": M0, "required": True},
    "Link[Org] = OoldField()": {"cls": M1, "required": True},
    "Optional[Link[Org]] = None": {"cls": M2, "required": False},
    "Link[Org] | None = None": {"cls": M3, "required": False},
    "Optional[Link[Org]] = OoldField()": {"cls": M4, "required": False},
    "Link[Org] = OoldField(required=False)": {"cls": M5, "required": False, "strict_read": True},
    "LinkList[Org]": {"cls": M6, "required": True, "many": True},
    "Optional[LinkList[Org]] = None": {"cls": M7, "required": False, "many": True},
    "LinkList[Org | None] = OoldField()": {"cls": M8, "required": False, "many": True},
    "LinkList[Org] = OoldField(required=False)": {"cls": M9, "required": False, "many": True, "strict_read": True},
    'Link[Org] = OoldField(default="mx:o1")': {"cls": M10, "required": False, "defaulted": True},
}

_CLASSES = {label: row["cls"] for label, row in ROWS.items()}


@pytest.mark.parametrize("label", ROWS)
def test_column_required(label):
    """Column *required*: construction without the link."""
    cls, row = _CLASSES[label], ROWS[label]
    if row["required"]:
        with pytest.raises(ValueError, match="f is required"):
            cls(id="mx:i")
    else:
        assert cls(id="mx:i").id == "mx:i"


@pytest.mark.parametrize("label", ROWS)
def test_column_in_required_array(label):
    """Column *in required[]*: the emitted schema states the same thing."""
    cls, row = _CLASSES[label], ROWS[label]
    assert ("f" in (cls.export_schema().get("required") or [])) is row["required"]


@pytest.mark.parametrize(
    "label",
    [label for label, row in ROWS.items() if not row["required"] and not row.get("defaulted")],
)
def test_column_unset_read(label):
    """Column *unset read*, for the rows that construct unset.

    A non-optional read type raises; an optional one answers None for a
    to-one and [] for a to-many ([] is "no elements", not "no list" - the
    None-list statement needs the value actually set to None, which an unset
    descriptor does not distinguish today; documented as a known gap).
    """
    cls, row = _CLASSES[label], ROWS[label]
    instance = cls(id="mx:i")
    if row.get("strict_read"):
        with pytest.raises(LinkNotSet):
            _ = instance.f
    elif row.get("many"):
        assert list(instance.f) == []
    else:
        assert instance.f is None


def test_required_rows_read_after_construction(linked_store):
    """Column *unset read* is unreachable for required rows - construction
    already demands the value - so the read contract is checked supplied."""
    linked_store("mx", {"mx:o1": {"id": "mx:o1", "type": "mx:Org"}})
    one = _CLASSES["Link[Org]"](id="mx:i", f="mx:o1")
    assert isinstance(one.f, Org)
    many = _CLASSES["LinkList[Org]"](id="mx:i", f=["mx:o1"])
    assert [type(v).__name__ for v in many.f] == ["Org"]


def test_a_required_list_accepts_an_explicitly_empty_one(linked_store):
    """JSON Schema `required` demands the key, and {"f": []} has it - so the
    schema the class emits accepts the document, and construction must too."""
    linked_store("mx", {})
    instance = _CLASSES["LinkList[Org]"](id="mx:i", f=[])
    assert list(instance.f) == []


def test_a_defaulted_link_is_not_required(linked_store):
    """A field with a default is never required in pydantic; the declared IRI
    is seeded instead and resolves lazily."""
    linked_store("mx", {"mx:o1": {"id": "mx:o1", "type": "mx:Org"}})
    cls = _CLASSES['Link[Org] = OoldField(default="mx:o1")']
    instance = cls(id="mx:i")  # constructs: the default satisfies the link
    assert instance.link_iris("f") == "mx:o1"
    assert isinstance(instance.f, Org)


def test_not_set_and_unresolvable_are_distinct(linked_store):
    """The two failure modes carry their own class; the base catches both."""
    linked_store("mx", {"mx:o1": {"id": "mx:o1", "type": "mx:Org"}})
    strict = _CLASSES["Link[Org] = OoldField(required=False)"]

    unset = strict(id="mx:i")
    with pytest.raises(LinkNotSet):
        _ = unset.f
    with pytest.raises(LinkNotResolved):
        _ = unset.f

    ghost = strict(id="mx:i", f="mx:ghost")
    with pytest.raises(LinkUnresolvable):
        _ = ghost.f
    with pytest.raises(LinkNotResolved):
        _ = ghost.f

    assert not issubclass(LinkNotSet, LinkUnresolvable)
    assert not issubclass(LinkUnresolvable, LinkNotSet)


def test_the_message_names_the_failing_hop(linked_store):
    """Every hop of a self-referential chain shares the class and attribute
    name, so the subject IRI is what identifies the failing one."""
    linked_store("mx", {})

    class Hop(LinkedBaseModel):
        model_config = ConfigDict(json_schema_extra={"$id": "https://example.org/mx/Hop"})
        id: str
        type: str | None = "mx:Hop"
        parent: Link["Hop"] = OoldField(required=False)

    Hop.model_rebuild()
    leaf = Hop(id="mx:leaf", parent={"id": "mx:mid", "type": "mx:Hop"})
    with pytest.raises(LinkNotSet, match=r"Hop\(mx:mid\)\.parent"):
        _ = leaf.parent.parent.parent

    ghost = Hop(id="mx:g0", parent="mx:ghost")
    with pytest.raises(LinkUnresolvable, match=r"Hop\(mx:g0\)\.parent.*mx:ghost"):
        _ = ghost.parent
