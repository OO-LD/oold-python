"""Static contract of the class-level query API - checked by pyright and ty.

Never imported at runtime; ``tests/test_typing.py`` runs both checkers over it
and fails on any diagnostic. ``Model[...]`` is typed by overloads on the
metaclass ``__getitem__``, which both checkers resolve.

The condition expression itself stays untyped: ``Entity.name`` is a declared
field, so pydantic's ``dataclass_transform`` makes the annotation authoritative
for class-level access and the ``FieldProxy`` returned at runtime is invisible,
leaving ``Entity.name == "x"`` as ``bool``. The subscript overloads accept
``bool`` for exactly that reason - the result type is right even though the
argument type is not.
"""

from typing_extensions import assert_type

from oold.model._descriptor import AutoLinkedModel, LinkResultList


class Entity(AutoLinkedModel):
    id: str
    name: str | None = None


# a single IRI yields one instance, a condition or a list of IRIs yields a list
assert_type(Entity["ex:e1"], Entity | None)
assert_type(Entity[Entity.name == "x"], LinkResultList[Entity] | None)
assert_type(Entity[["ex:e1", "ex:e2"]], LinkResultList[Entity] | None)

many = Entity[Entity.name == "x"]
if many is not None:
    # indexing and filtering keep the item type. Elements are not optional:
    # a query answers with what it found, so an IRI it could not place is
    # dropped rather than kept as a None
    assert_type(many[0], Entity)
    assert_type(many[0:2], LinkResultList[Entity])
    assert_type(many[Entity.name == "y"], LinkResultList[Entity])
    assert_type(many[0].name, str | None)
