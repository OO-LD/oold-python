from typing import List, Optional


def _run(pydantic_version):
    if pydantic_version == "v1":
        from pydantic.v1 import Field

        from oold.model.v1 import LinkedBaseModel  # based on pydantic v2

        class Entity(LinkedBaseModel):
            class Config:
                schema_extra = {
                    "@context": {
                        # aliases
                        "id": "@id",
                        "type": "@type",
                        # prefixes
                        "schema": "https://schema.org/",
                        "ex": "https://example.com/",
                        # literal property
                        "name": "schema:name",
                    },
                    "iri": "Entity.json",  # the IRI of the schema
                }

            type: Optional[str] = "ex:Entity"
            name: str

            def get_iri(self):
                return "ex:" + self.name

        class Person(Entity):
            class Config:
                schema_extra = {
                    "@context": [
                        "Entity.json",  # import the context of the parent class
                        {
                            # object property definition
                            "knows": {"@id": "schema:knows", "@type": "@id"},
                        },
                    ],
                    "iri": "Person.json",
                }

            type: Optional[str] = "ex:Person"
            knows: Optional[List["Person"]] = Field(
                None,
                # object property pointing to another Person
                json_schema_extra={"range": "Person.json"},
            )

    if pydantic_version == "v2":
        from pydantic import ConfigDict, Field

        from oold.model import LinkedBaseModel  # based on pydantic v2

        class Entity(LinkedBaseModel):
            model_config = ConfigDict(
                json_schema_extra={
                    "@context": {
                        # aliases
                        "id": "@id",
                        "type": "@type",
                        # prefixes
                        "schema": "https://schema.org/",
                        "ex": "https://example.com/",
                        # literal property
                        "name": "schema:name",
                    },
                    "iri": "Entity.json",  # the IRI of the schema
                }
            )
            type: Optional[str] = "ex:Entity"
            name: str

            def get_iri(self):
                return "ex:" + self.name

        class Person(Entity):  # noqa
            model_config = ConfigDict(
                json_schema_extra={
                    "@context": [
                        "Entity.json",  # import the context of the parent class
                        {
                            # object property definition
                            "knows": {"@id": "schema:knows", "@type": "@id"},
                        },
                    ],
                    "iri": "Person.json",
                }
            )
            type: Optional[str] = "ex:Person"
            knows: Optional[List["Person"]] = Field(
                None,
                # object property pointing to another Person
                json_schema_extra={"range": "Person.json"},
            )

    p1 = Person(name="Alice")
    p2 = Person(name="Bob", knows=[p1])
    print(p2.to_jsonld())

    # load the rdf into a rdflib graph
    from rdflib import Graph

    g = Graph()
    g.parse(data=p1.to_jsonld(), format="json-ld")
    g.parse(data=p2.to_jsonld(), format="json-ld")
    print(g.serialize(format="turtle"))

    # query the name of persons that Bob knows
    qres = g.query(
        """
        SELECT ?name
        WHERE {
            ?s <https://schema.org/knows> ?o .
            ?o <https://schema.org/name> ?name .
        }
        """
    )
    for row in qres:
        print("Bob knows " + row.name)
        assert str(row.name) == "Alice"


def test_rdf_export_and_sparql_query():
    _run("v1")
    _run("v2")


if __name__ == "__main__":
    test_rdf_export_and_sparql_query()
