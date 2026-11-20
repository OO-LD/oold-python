"""Static contract of a link field - checked by pyright and ty.

Never imported at runtime; ``tests/test_typing.py`` runs both checkers over it
and fails on any diagnostic.

A link has two types, and one annotation cannot state both: what you read is a
resolved object, what you may write is that object *or* a reference to it - an
IRI string, or a JSON object still to be constructed. ``Link[T]`` and
``LinkList[T]`` carry both by being descriptors, so a checker takes the
``__init__`` parameter and the assignment type from ``__set__`` and the attribute
type from ``__get__`` (PEP 681).

Optionality follows the annotation, as it does for every other pydantic field.
A bare ``Link[T]`` is required and reads as ``T`` - the binding keeps that
promise by raising rather than returning a ``None`` the type denies, which is
what lets a chain of mandatory links be written without a guard at every hop.
``Optional[Link[T]] = None`` is the optional form and reads as ``T | None``,
because absence is then part of the model.

The read-type and filter columns of the notation table in
``docs/how-to/object-graph-mapping.md`` are asserted here; the runtime columns
live in ``tests/test_link_notation_matrix.py``.
"""

from typing import Any

from typing_extensions import assert_type

from oold.model import Link, LinkedBaseModel, LinkList, LinkResultList, OoldField


class Org(LinkedBaseModel):
    id: str
    name: str | None = None


class Entity(LinkedBaseModel):
    id: str
    name: str | None = None
    # required: the bare annotation, exactly like a bare `x: int`
    owner: Link[Org]
    parent: Link["Entity"]
    links: LinkList["Entity"]
    # required with field kwargs: OoldField() does not change requiredness
    boss: Link[Org] = OoldField(description="demonstrates field kwargs")
    # optional: absence is data, declared as everywhere else in pydantic
    sponsor: Link[Org] | None = None
    other: Link[Org] | None = None
    # to-many, three distinct statements
    maybe_links: LinkList["Entity | None"] = OoldField()  # an element may be absent
    no_list: LinkList["Entity"] | None = None  # the list itself may be absent
    # plain spelling: runtime-identical, but a checker only sees list[Entity]
    plain: list["Entity"] = OoldField()


# -- writes: an object, an IRI or a JSON object are all accepted -------------
written = Entity(
    id="ex:e1",
    owner="ex:acme",
    parent={"id": "ex:p"},
    links=["ex:a", Entity(id="ex:b", owner="ex:acme", parent="ex:p", links=[]), {"id": "ex:c"}],
    sponsor=None,
)
written.links = ["ex:d", {"id": "ex:e"}]
written.owner = {"id": "ex:other"}
# Attribute writes through the Optional wrapper are pyright-only: ty does not
# apply the descriptor's __set__ inside a union (0.0.49 rejected the reference
# forms, 0.0.107 rejects every assignment including None), so the probe asserts
# the constructor direction, which both checkers type, and the runtime
# acceptance of all reference forms is covered by
# tests/test_link_notation_matrix.py.

# -- reads: exactly what the annotation declares ------------------------------
# A separate instance: ty narrows an attribute to the assigned type after a
# write, which would otherwise mask what __get__ declares.
read = Entity(id="ex:e2", owner="ex:acme", parent="ex:p", links=[])
assert_type(read.owner, Org)
assert_type(read.boss, Org)
assert_type(read.links, LinkResultList[Entity])
assert_type(read.links[0], Entity)
assert_type(read.links[0].name, str | None)

# the point of a required link: chaining needs no guard per hop
assert_type(read.parent.parent.parent, Entity)
assert_type(read.parent.parent.owner.name, str | None)

# declared optional, so the guard is required - and warranted
assert_type(read.sponsor, Org | None)
assert_type(read.other, Org | None)
sponsor = read.sponsor
if sponsor is not None:
    assert_type(sponsor.name, str | None)

# -- the list-access and filter columns ---------------------------------------
# element access and filters preserve the declared element type
assert_type(read.links[0:2], LinkResultList[Entity])
assert_type(read.links[Entity.name == "x"], LinkResultList[Entity])
assert_type(read.links["@name=='x'"], Any)  # the string form ends type checking

assert_type(read.maybe_links, LinkResultList[Entity | None])
assert_type(read.maybe_links[0], Entity | None)
assert_type(read.maybe_links[0:2], LinkResultList[Entity | None])
assert_type(read.maybe_links[Entity.name == "x"], LinkResultList[Entity | None])

# the absent-list form must be gated before any subscript
assert_type(read.no_list, LinkResultList[Entity] | None)
no_list = read.no_list
if no_list is not None:
    assert_type(no_list[0], Entity)
    assert_type(no_list[Entity.name == "x"], LinkResultList[Entity])

# The plain spelling reads as declared - which is why an IRI cannot be assigned
# to it statically, and why it cannot express either promise.
assert_type(read.plain, list[Entity])
