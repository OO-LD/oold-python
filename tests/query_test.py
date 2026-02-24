import time
from typing import List, Optional

import pytest

from oold.backend.document_store import SimpleDictDocumentStore
from oold.backend.interface import Query, SetBackendParam, set_backend


def _define_entity(pydantic_version):
    """Define the Entity class for the given pydantic version."""
    if pydantic_version == "v1":
        from pydantic.v1 import Field

        from oold.model.v1 import LinkedBaseModel, LinkedBaseModelList

        class Entity(LinkedBaseModel):
            """A simple Entity schema"""

            class Config:
                schema_extra = {
                    "@context": {
                        "ex": "http://example.org/",
                        "id": "@id",
                        "type": "@type",
                        "name": "ex:name",
                        "links": {
                            "@id": "ex:links",
                            "@type": "@id",
                            "@container": "@set",
                        },
                    },
                    "iri": "ex:Entity",
                }

            id: str
            """The IRI of the entity."""
            name: str
            """The name of the entity."""
            type: Optional[str] = "ex:Entity"
            """The type of the entity."""
            links: Optional[List["Entity"]] = Field(
                None,
                range="ex:Entity",
            )
            """links to other entities"""

    else:
        from pydantic import Field

        from oold.model import LinkedBaseModel, LinkedBaseModelList

        class Entity(LinkedBaseModel):
            """A simple Entity schema"""

            model_config = {
                "json_schema_extra": {
                    "@context": {
                        "ex": "http://example.org/",
                        "id": "@id",
                        "type": "@type",
                        "name": "ex:name",
                        "links": {
                            "@id": "ex:links",
                            "@type": "@id",
                            "@container": "@set",
                        },
                    },
                    "iri": "ex:Entity",
                }
            }

            id: str
            """The IRI of the entity."""
            name: str
            """The name of the entity."""
            type: Optional[str] = "ex:Entity"
            """The type of the entity."""
            links: Optional[List["Entity"]] = Field(
                None,
                json_schema_extra={
                    "range": "ex:Entity",
                },
            )
            """links to other entities"""

    return Entity, LinkedBaseModelList


def _run_queries(pydantic_version):
    Entity, LinkedBaseModelList = _define_entity(pydantic_version)

    backend = SimpleDictDocumentStore()
    set_backend(SetBackendParam(iri="ex", backend=backend))

    e1 = Entity(id="ex:e1", name="Entity 1")
    e2 = Entity(id="ex:e2", name="Entity 1")
    e1.store_jsonld()
    e2.store_jsonld()

    q = (Entity.name == "test") & (Entity.id == "ex:e1")
    assert type(q) is Query

    r1 = Entity[Entity.name == "Entity 1"]
    assert len(r1) == 2

    r2 = Entity[Entity.id == "ex:e1"]
    assert len(r2) == 1
    assert r2[0].id == "ex:e1"

    r3 = Entity[(Entity.name == "Entity 1") & (Entity.id == "ex:e2")]
    assert len(r3) == 1
    assert r3[0].id == "ex:e2"


def _run_linked_base_model_list(pydantic_version):
    Entity, LinkedBaseModelList = _define_entity(pydantic_version)

    # test LinkedBaseModelList IRI synchronization
    synced_iri_list = []
    el = LinkedBaseModelList[Entity](
        [Entity(id="ex:e1", name="Entity 1"), Entity(id="ex:e2", name="Entity 2")],
        _synced_iri_list=synced_iri_list,
    )
    assert synced_iri_list == ["ex:e1", "ex:e2"]
    el.append(Entity(id="ex:e3", name="Entity 3"))
    assert synced_iri_list == ["ex:e1", "ex:e2", "ex:e3"]
    el.remove(Entity(id="ex:e2", name="Entity 2"))
    assert synced_iri_list == ["ex:e1", "ex:e3"]
    el.extend(
        [Entity(id="ex:e4", name="Entity 4"), Entity(id="ex:e5", name="Entity 5")]
    )
    assert synced_iri_list == ["ex:e1", "ex:e3", "ex:e4", "ex:e5"]

    assert el[0].id == "ex:e1"
    assert el["ex:e3"].name == "Entity 3"

    # test string queries
    result = el["@name=='Entity 3'"]
    assert result[0].id == "ex:e3"

    # test Condition-based queries
    assert el[Entity.name == "Entity 3"][0].id == "ex:e3"

    # test linked entities with IRI sync on attribute access
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
    assert e3.links[(Entity.name == "Entity 1")] is not None
    assert e3.links[Entity.name == "Entity 1"][0].id == "ex:e1"

    assert [e for e in e3.links if e.name == "Entity 1"][0].id == "ex:e1"

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


def _run_performance(pydantic_version):
    Entity, LinkedBaseModelList = _define_entity(pydantic_version)

    # create 3 layers of entities with 333 entities each
    # connect each node on a layer with all nodes on the next layer
    layers = 3
    entities_per_layer = 333
    all_entities = []

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
    total_links = sum(
        len(e.links) if e.links else 0 for layer in all_entities for e in layer
    )
    print(
        f"[{pydantic_version}] Created"
        f" {layers * entities_per_layer} entities with"
        f" {total_links} links"
        f" in {end_time - start_time:.2f} seconds"
    )

    layer1 = LinkedBaseModelList[Entity](all_entities[0])

    start_time = time.time()
    res = (
        layer1[Entity.name == "Entity 0-50"]
        .links[Entity.name == "Entity 1-50"]
        .links[Entity.name == "Entity 2-50"]
    )
    end_time = time.time()
    assert res[0].name == "Entity 2-50"
    elapsed = end_time - start_time
    print(f"[{pydantic_version}] Accessed a specific link" f" in {elapsed:.6f} seconds")


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_queries(pydantic_version):
    _run_queries(pydantic_version)


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_linked_base_model_list(pydantic_version):
    _run_linked_base_model_list(pydantic_version)


@pytest.mark.parametrize("pydantic_version", ["v1", "v2"])
def test_performance_large_linked_structure(pydantic_version):
    _run_performance(pydantic_version)


if __name__ == "__main__":
    _run_queries("v1")
    _run_queries("v2")
    _run_linked_base_model_list("v1")
    _run_linked_base_model_list("v2")
    _run_performance("v1")
    _run_performance("v2")
