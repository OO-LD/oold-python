"""Static contract of a link field - checked by pyright and ty.

Never imported at runtime; ``tests/test_typing.py`` runs both checkers over it
and fails on any diagnostic.

A link has two types, and one annotation cannot state both: what you read is a
resolved object, what you may write is that object *or* a reference to it - an
IRI string, or a JSON object still to be constructed. ``Link[T]`` and
``LinkList[T]`` carry both by being descriptors, so a checker takes the
``__init__`` parameter and the assignment type from ``__set__`` and the attribute
type from ``__get__`` (PEP 681).

Elements are ``T | None``: an IRI the backend cannot answer resolves to ``None``
and keeps its slot, so a guard at the use site is warranted.
"""

from typing_extensions import assert_type

from oold.model._descriptor import AutoLinkedModel, Link, LinkList, LinkResultList, OoldField


class Org(AutoLinkedModel):
    id: str
    name: str | None = None


class Entity(AutoLinkedModel):
    id: str
    name: str | None = None
    # covered spelling: typed in both directions
    links: LinkList["Entity"] = OoldField()
    owner: Link[Org] = OoldField()
    # plain spelling: runtime-identical, but a checker only sees list[Entity]
    plain: list["Entity"] = OoldField()


# -- writes: an object, an IRI or a JSON object are all accepted -------------
written = Entity(
    id="ex:e1",
    links=["ex:a", Entity(id="ex:b"), {"id": "ex:c"}],
    owner="ex:acme",
)
written.links = ["ex:d", {"id": "ex:e"}]
written.owner = {"id": "ex:other"}

# -- reads: narrow, and honest about unresolvable references -----------------
# A separate instance: ty narrows an attribute to the assigned type after a
# write, which would otherwise mask what __get__ declares.
read = Entity(id="ex:e2")
assert_type(read.links, LinkResultList[Entity])
assert_type(read.links[0], Entity | None)
assert_type(read.owner, Org | None)

first = read.links[0]
if first is not None:
    assert_type(first.name, str | None)

owner = read.owner
if owner is not None:
    assert_type(owner.name, str | None)

# The plain spelling reads as declared - which is why it cannot report that an
# element may be None, and why an IRI cannot be assigned to it statically.
assert_type(read.plain, list[Entity])
