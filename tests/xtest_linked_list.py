# create a subtype of list that tracks changes

from typing import (
    Any,
    Generic,
    List,
    Optional,
    Self,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

import pandas as pd
from typing_extensions import get_args

from oold.model import LinkedBaseModel
from oold.model.v1 import LinkedBaseModel as LinkedBaseModel_v1

# mini example pandas filter
df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
df_filtered = df[df["A"] == 2]


from pydantic import BaseModel, Field, GetCoreSchemaHandler
from pydantic_core import core_schema


class Query(BaseModel):
    field: str
    operator: Optional[str] = None
    value: Optional[Union[str, int, float]] = None

    def __eq__(self, other):
        self.operator = "eq"
        self.value = other
        return self


from oold.model import LinkedBaseModelMetaClass


class TestMetaClass(LinkedBaseModelMetaClass):
    # # replace List type annotations with LinkedBaseModelList
    # def __new__(cls, name, bases, namespace, **kwargs):
    #     for key, value in namespace.get('__annotations__', {}).items():
    #         # handle List[]
    #         if value == List:
    #             #namespace['__annotations__'][key] = LinkedBaseModelList
    #             print(f"Replacing {key}: {value} with LinkedBaseModelList")
    #         # handle Optional[List[]]
    #         elif value == Optional:
    #             args = get_args(value)
    #             if len(args) == 2 and args[1] == type(None) and str(args[0]).startswith('typing.List'):
    #                 inner_type = get_args(args[0])[0]
    #                 print(f"Replacing {key}: {value} with LinkedBaseModelList[{inner_type}]")
    #                 #namespace['__annotations__'][key] = Optional[LinkedBaseModelList[inner_type]]

    #     return super().__new__(cls, name, bases, namespace, **kwargs)

    def __getattribute__(self, name):
        # print(f"Accessing attribute {name}")
        if name not in ["__bases__", "model_fields", "__pydantic_fields__", "__dict__"]:
            # check if attribute is in fields
            if name in self.model_fields:
                # print(f"Attribute {name} is in model fields")
                return Query(field=name)
        return super().__getattribute__(name)

    # this works but not with static type checkers
    # cannot use cls as type annotation
    # update: seams to work
    # @overload
    def __getitem__(cls, index: Query) -> Optional[List[Self]]:
        print(f"Select all {cls.__name__} that match {index}")
        return cls(id="ex:test", name="test")

    # # @ operator

    # @classmethod
    # def __matmul__(self, other: str) -> Optional[List[Self]]:
    #     print(f"Matmul operator called with {other}")
    # @classmethod
    # def __rmatmul__(self, other: str) -> Optional[List[Self]]:
    #     print(f"Matmul operator called with {other}")

    # __array_priority__ = 100


T = TypeVar("T")  # , LinkedBaseModel, LinkedBaseModel_v1)


class LinkedBaseModelList(Generic[T], List[Optional[T]]):
    """Extension of list that tracks changes to the list.
    by syncing every modification with the __iri__ field of the parent model."""

    def __init__(
        self, *args: Optional[T], _synced_iri_list: Optional[List[str]] = None
    ):
        super().__init__(*args)
        self._synced_iri_list = (
            _synced_iri_list  # if _synced_iri_list is not None else []
        )
        # self._synced_iri_list.extend(item.get_iri() for item in self if item is not None)
        # initialize the synced_iri_list with the IRIs of the initial items in the list
        if self._synced_iri_list is not None:
            self._synced_list = args[0]
            self._synced_iri_list.extend(
                item.get_iri()
                for item in self
                if item.get_iri() not in self._synced_iri_list and item is not None
            )

    # def _set_synced_iri_list(self, iri_list: List[str]) -> None:
    #     """Set the list of IRIs that are synced with the linked data store."""
    #     self._synced_iri_list = iri_list

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        instance_schema = core_schema.is_instance_schema(cls)

        args = get_args(source)
        if args:
            # replace the type and rely on Pydantic to generate the right schema
            # for `Sequence`
            sequence_t_schema = handler.generate_schema(List[args[0]])
        else:
            sequence_t_schema = handler.generate_schema(List)

        non_instance_schema = core_schema.no_info_after_validator_function(
            LinkedBaseModelList, sequence_t_schema
        )
        return core_schema.union_schema([instance_schema, non_instance_schema])

    def append(self, item: Optional[T]) -> None:
        if self._synced_iri_list is not None:
            self._synced_iri_list.append(item.get_iri())
            self._synced_list.append(item)
        super().append(item)

    def remove(self, item: Optional[T]) -> None:
        if self._synced_iri_list is not None:
            self._synced_iri_list.remove(item.get_iri())
            self._synced_list.remove(item)
        super().remove(item)

    def extend(self, iterable):
        if self._synced_iri_list is not None:
            self._synced_iri_list.extend(
                item.get_iri() for item in iterable if item is not None
            )
            self._synced_list.extend(iterable)
        return super().extend(iterable)

    def get_item_type(self):
        # Returns the actual type argument, e.g. Entity
        if hasattr(self, "__orig_class__"):
            return get_args(self.__orig_class__)[0]
        return None

    # override [] operator to also support string indices

    @overload
    def __getitem__(self, index: str) -> Optional[Union[T, "LinkedBaseModelList[T]"]]:
        ...

    @overload
    def __getitem__(self, index: bool) -> Optional[Union[T, "LinkedBaseModelList[T]"]]:
        ...

    @overload
    def __getitem__(self, index: int) -> Optional[T]:
        ...

    # allow pandas-style queries, e.g. l[Entity.name=='John']
    @overload
    def __getitem__(self, index: Query) -> Optional[Union[T, "LinkedBaseModelList[T]"]]:
        ...

    def __getitem__(self, index):
        if isinstance(index, str):
            if index.startswith("@"):
                # query, e.g. "@name=='John'"
                key = index[1:].split("==")[0].strip()
                value = index.split("==")[1].strip("'\"")
                return LinkedBaseModelList[self.get_item_type()](
                    [
                        item
                        for item in self
                        if item and getattr(item, key, None) == value
                    ],
                    _synced_iri_list=self._synced_iri_list,
                )

            else:
                # IRI lookup
                for item in self:
                    if item and item.get_iri() == index:
                        return item
                raise KeyError(f"No item with IRI {index} found")
        elif isinstance(index, Query):
            key = index.field
            operator = index.operator
            value = index.value
            if operator == "eq":
                return LinkedBaseModelList[self.get_item_type()](
                    [
                        item
                        for item in self
                        if item and getattr(item, key, None) == value
                    ],
                    _synced_iri_list=self._synced_iri_list,
                )
            else:
                raise NotImplementedError(f"Operator {operator} not implemented")
        else:
            return super().__getitem__(index)

    def __getattribute__(self, name):
        if not name == "__orig_class__":
            # if name == "links":
            #    print(typing.get_args(self))
            if hasattr(self, "__orig_class__"):
                _type = get_args(self.__orig_class__)[0]
                if name in _type.model_fields.keys():
                    # print(f"Attribute {name} is in type {_type}")
                    # build a new LinkedBaseModelList with all the values of this attribute
                    # if attribute is List
                    result_list = LinkedBaseModelList[_type]([], _synced_iri_list=None)
                    for item in self:
                        if item is not None and hasattr(item, name):
                            value = getattr(item, name)
                            if isinstance(value, list):
                                result_list.extend(value)
                            else:
                                result_list.append(value)
                    return result_list

        # else:
        return super().__getattribute__(name)


class TestLinkedBaseModel(LinkedBaseModel, metaclass=TestMetaClass):
    def __getattribute__(self, name):
        result = super().__getattribute__(name)
        if isinstance(result, list) and name in self.__iris__:
            result = LinkedBaseModelList[type(self)](
                result, _synced_iri_list=self.__iris__[name]
            )
        return result

    # @overload
    # def __get_item__(self, index: str) -> Optional[List[cls]]

    # does not work, conflic with Generic[T]
    # type error: cannot be parametrized because it does not inherit from typing.Generic
    # @classmethod
    # @staticmethod
    # def __getitem__(cls, index) -> Optional[List[Self]]:
    #     print(f"Select all entities that match {index}")

    # works, but not with static type checkers
    # https://github.com/python/mypy/issues/11501
    # def __class_getitem__(cls, index) -> Optional[List[Self]]:
    #     print(f"Select all {cls.__name__} that match {index}")
    #     return cls(id="ex:test", name="test")


import typing

typing.List = LinkedBaseModelList


class Entity(TestLinkedBaseModel):
    """A simple Entity schema"""

    id: str
    """The IRI of the entity."""
    name: str
    """The name of the entity."""
    # links: Optional[List["Entity"]] = Field(
    links: Optional[LinkedBaseModelList["Entity"]] = Field(
        None,
        json_schema_extra={
            "range": "ex:Entity",
        },
    )
    """links to other entities"""


te = Entity[Entity.name == "test"]
te
# te2 = Entity.__class_getitem__("test")
print(te.name)

# works
# te3 = LinkedBaseModelList[Entity]()[Entity.name == "test"]

# te[0].

# te2 = Entity @ "@name=='Entity 1'"
# te = Entity.__matmul__("@name=='Entity 1'")

e = Entity(id="ex:e1", name="Entity 1")
e.get_iri()

# test BaseModel
synced_iri_list = []
l = LinkedBaseModelList[Entity](
    [Entity(id="ex:e1", name="Entity 1"), Entity(id="ex:e2", name="Entity 2")],
    _synced_iri_list=synced_iri_list,
)
assert synced_iri_list == ["ex:e1", "ex:e2"]
l.append(Entity(id="ex:e3", name="Entity 3"))
assert synced_iri_list == ["ex:e1", "ex:e2", "ex:e3"]
l.remove(Entity(id="ex:e2", name="Entity 2"))
assert synced_iri_list == ["ex:e1", "ex:e3"]
l.extend([Entity(id="ex:e4", name="Entity 4"), Entity(id="ex:e5", name="Entity 5")])
assert synced_iri_list == ["ex:e1", "ex:e3", "ex:e4", "ex:e5"]

assert l[0].id == "ex:e1"
assert l["ex:e3"].name == "Entity 3"

# test queries
result = l["@name=='Entity 3'"]
assert result[0].id == "ex:e3"

# test Query
co = Entity.name == "Entity 3"
assert l[Entity.name == "Entity 3"][0].id == "ex:e3"

e1 = Entity(name="Entity 1", id="ex:e1")
e2 = Entity(name="Entity 2", id="ex:e2", links=[e1])
e3 = Entity(name="Entity 3", id="ex:e3", links=[e1, e2])

assert e2.__iris__["links"] == ["ex:e1"]
e2.links.append(e3)
assert e2.links == [e1, e3]
assert e2.__iris__["links"] == ["ex:e1", "ex:e3"]
e2.links.remove(e1)
assert e2.__iris__["links"] == ["ex:e3"]
e2.links.extend([e1])
assert e2.__iris__["links"] == ["ex:e3", "ex:e1"]

assert e3.links[0].id == "ex:e1"
assert e3.links["@name=='Entity 2'"][0].id == "ex:e2"
test = e3.links[(Entity.name == "Entity 1")]
assert e3.links[Entity.name == "Entity 1"][0].id == "ex:e1"

links = [e for e in e3.links if e.name == "Entity 1"]

# test multi chain
assert (
    e3.links[Entity.name == "Entity 2"][0].links[Entity.name == "Entity 1"][0].id
    == "ex:e1"
)
assert (
    e3.links[Entity.name == "Entity 2"].links[Entity.name == "Entity 1"][0].id
    == "ex:e1"
)

e3.links[Entity.name == "Entity 2"].links[Entity.name == "Entity 1"].name

res = e3.links[Entity.name == "Entity 2"].links[Entity.name == "Entity 1"]
assert res[0].id == "ex:e1"

# performance test
import time

# create 3 layers of entities with 100 entities each
# connect each node on a layer with all nodes on the next layer
layers = 3
entities_per_layer = 333
all_entities = []

# measure time to create the entities and link them
start_time = time.time()
for layer in range(layers):
    layer_entities = []
    for i in range(entities_per_layer):
        e = Entity(name=f"Entity {layer}-{i}", id=f"ex:e{i}")
        layer_entities.append(e)
    all_entities.append(layer_entities)
    if layer > 0:
        for parent in all_entities[layer - 1]:
            parent.links = layer_entities
end_time = time.time()
print(
    f"Created {layers * entities_per_layer} entities with number of links {sum(len(e.links) if e.links else 0 for layer in all_entities for e in layer)} in {end_time - start_time:.2f} seconds"
)

layer1 = LinkedBaseModelList[Entity](all_entities[0])

# mean time to access a specific link
start_time = time.time()
res = (
    layer1[Entity.name == "Entity 0-50"]
    .links[Entity.name == "Entity 1-50"]
    .links[Entity.name == "Entity 2-50"]
)
end_time = time.time()
assert res[0].name == "Entity 2-50"
print(f"Accessed a specific link in {end_time - start_time:.6f} seconds")
