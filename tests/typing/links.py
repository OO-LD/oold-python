"""Static contract of a link field - checked by pyright and ty.

Never imported at runtime; ``tests/test_typing.py`` runs both checkers over it
and fails on any diagnostic.

A link has two types, and one annotation cannot state both: what you read is a
resolved object, what you may write is that object *or* a reference to it - an
IRI string, or a JSON object still to be constructed. ``Link[T]`` and
``LinkList[T]`` carry both by being descriptors, so a checker takes the
``__init__`` parameter and the assignment type from ``__set__`` and the attribute
type from ``__get__`` (PEP 681).

Optionality is **declared**, not assumed. ``Link[T]`` reads as ``T`` and the
binding keeps that promise - a reference that cannot be resolved raises rather
than returning a ``None`` the type denies. ``Link[T | None]`` reads as
``T | None``, because absence is then part of the model. That is what lets a
chain of mandatory links be written without a guard at every hop.
"""

from typing_extensions import assert_type

from oold.model._descriptor import AutoLinkedModel, Link, LinkList, LinkResultList, OoldField


class Org(AutoLinkedModel):
    id: str
    name: str | None = None


class Entity(AutoLinkedModel):
    id: str
    name: str | None = None
    # mandatory: every reference resolves, or the read raises
    owner: Link[Org] = OoldField()
    parent: Link["Entity"] = OoldField()
    links: LinkList["Entity"] = OoldField()
    # optional: absence is data
    sponsor: Link["Org | None"] = OoldField()
    maybe_links: LinkList["Entity | None"] = OoldField()
    # plain spelling: runtime-identical, but a checker only sees list[Entity]
    plain: list["Entity"] = OoldField()


# -- writes: an object, an IRI or a JSON object are all accepted -------------
written = Entity(
    id="ex:e1",
    links=["ex:a", Entity(id="ex:b"), {"id": "ex:c"}],
    owner="ex:acme",
    sponsor=None,
)
written.links = ["ex:d", {"id": "ex:e"}]
written.owner = {"id": "ex:other"}

# -- reads: exactly what was declared ---------------------------------------
# A separate instance: ty narrows an attribute to the assigned type after a
# write, which would otherwise mask what __get__ declares.
read = Entity(id="ex:e2")
assert_type(read.owner, Org)
assert_type(read.links, LinkResultList[Entity])
assert_type(read.links[0], Entity)
assert_type(read.links[0].name, str | None)

# the point of declaring a link mandatory: chaining needs no guard per hop
assert_type(read.parent.parent.parent, Entity)
assert_type(read.parent.parent.owner.name, str | None)

# declared optional, so the guard is required - and warranted
assert_type(read.sponsor, Org | None)
assert_type(read.maybe_links[0], Entity | None)
sponsor = read.sponsor
if sponsor is not None:
    assert_type(sponsor.name, str | None)

# The plain spelling reads as declared - which is why an IRI cannot be assigned
# to it statically, and why it cannot express either promise.
assert_type(read.plain, list[Entity])
