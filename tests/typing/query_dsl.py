"""Static contract of the query DSL, checked by pyright.

Never imported at runtime - ``tests/test_typing.py`` runs pyright over this
file and fails on any diagnostic. It pins what a type checker sees, which unit
tests cannot: ``Entity["ex:e1"]`` used to be a *type error* ("Expected no type
arguments for class Entity") even though it worked at runtime.

The condition expression itself still reads as ``bool`` - ``Entity.name`` is a
declared field, so pydantic's ``dataclass_transform`` makes the annotation
authoritative for class-level access too, and the ``FieldProxy`` returned at
runtime is invisible to the checker. The subscript overloads accept ``bool`` for
exactly that reason, so the *result* type is right even though the argument type
is not.
"""

from pydantic import Field
from typing_extensions import assert_type

from oold.model._descriptor import AutoLinkedModel, LinkResultList


class Entity(AutoLinkedModel):
    id: str
    name: str | None = None
    links: LinkResultList["Entity"] = Field(default_factory=LinkResultList, json_schema_extra={"range": "Entity"})


# a single IRI yields one instance
assert_type(Entity["ex:e1"], Entity | None)
# a condition yields a list of them
assert_type(Entity[Entity.name == "x"], LinkResultList[Entity] | None)
# so does a list of IRIs
assert_type(Entity[["ex:e1", "ex:e2"]], LinkResultList[Entity] | None)

many = Entity[Entity.name == "x"]
if many is not None:
    assert_type(many[0], Entity)
    assert_type(many[0].name, str | None)
    assert_type(many[0:2], LinkResultList[Entity])
    # filtering a result list keeps the item type
    assert_type(many[Entity.name == "y"], LinkResultList[Entity])

# a to-many link annotated as LinkResultList filters and indexes the same way
entity = Entity(id="ex:e1")
assert_type(entity.links[Entity.name == "x"], LinkResultList[Entity])
assert_type(entity.links[0], Entity)
