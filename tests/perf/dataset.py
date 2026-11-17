"""Deterministic datasets for the RDF performance scenarios.

The scale unit is the triple, not the entity: each person contributes one type
triple, one name triple and one triple per ``knows`` edge.
"""

from pydantic import ConfigDict, Field

TRIPLE_SIZES = (1_000, 10_000, 100_000)
# The intermediate sizes give a scaling exponent even for a scenario too slow to reach 10k.
BENCHMARK_SIZES = (1_000, 2_000, 4_000, 10_000, 100_000)
PREFIX = "perf"
NAMESPACE = "https://perf.example.org/"
BASE_TRIPLES = 2


def build_person_model():
    """Define the Person model. Call it inside the test or run that needs it.

    Defining it registers the class by type IRI, so the conftest fixture that
    restores the registries must be active.
    """
    from oold.model import LinkedBaseModel

    class Entity(LinkedBaseModel):
        model_config = ConfigDict(
            json_schema_extra={
                "@context": {
                    "id": "@id",
                    "type": "@type",
                    "schema": "https://schema.org/",
                    PREFIX: NAMESPACE,
                    "name": "schema:name",
                },
                "$id": f"{NAMESPACE}Entity",
            }
        )
        type: str | None = f"{PREFIX}:Entity"
        name: str

        def get_iri(self):
            return f"{PREFIX}:{self.name}"

    class Person(Entity):
        model_config = ConfigDict(
            json_schema_extra={
                "@context": [
                    f"{NAMESPACE}Entity",
                    {"knows": {"@id": "schema:knows", "@type": "@id", "@container": "@set"}},
                ],
                "$id": f"{NAMESPACE}Person",
            }
        )
        type: str | None = f"{PREFIX}:Person"
        knows: list["Person"] | None = Field(None, json_schema_extra={"range": f"{PREFIX}:Person"})

    return Person


def edges_per_person(triples: int, knows: int = 2) -> list[int]:
    """Edge count per person so the dataset has exactly ``triples`` triples."""
    per_person = BASE_TRIPLES + knows
    people = triples // per_person
    if people <= knows + 1:
        raise ValueError(f"{triples} triples is too few for {knows} edges per person")
    counts = [knows] * people
    for i in range(triples - people * per_person):
        counts[i] += 1
    return counts


def make_people(person_cls, triples: int, knows: int = 2) -> list:
    """Persons ``p0..pN`` where person i knows the next persons, wrapping around.

    Edges are IRI strings, so the people can be built in any order.
    """
    counts = edges_per_person(triples, knows)
    total = len(counts)
    return [
        person_cls(
            name=f"p{i}",
            knows=[f"{PREFIX}:p{(i + step) % total}" for step in range(1, edges + 1)],
        )
        for i, edges in enumerate(counts)
    ]
