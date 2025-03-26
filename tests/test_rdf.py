import json
from typing import List, Optional


def _run(pydantic_version):
    if pydantic_version == "v1":
        from pydantic.v1 import Field

        # based on pydantic v1
        from oold.model.v1 import (
            LinkedBaseModel,
            ResolveParam,
            Resolver,
            ResolveResult,
            SetResolverParam,
            set_resolver,
        )

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

            type: Optional[str] = "ex:Entity.json"
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
                            "knows": {
                                "@id": "schema:knows",
                                "@type": "@id",
                                "@container": "@set",
                            }
                        },
                    ],
                    "iri": "Person.json",
                }

            type: Optional[str] = "ex:Person.json"
            knows: Optional[List["Person"]] = Field(
                None,
                # object property pointing to another Person
                range="Person.json",
            )

    if pydantic_version == "v2":
        from pydantic import ConfigDict, Field

        # based on pydantic v2
        from oold.model import LinkedBaseModel  # noqa
        from oold.model import ResolveParam  # noqa
        from oold.model import Resolver  # noqa
        from oold.model import ResolveResult  # noqa
        from oold.model import SetResolverParam  # noqa
        from oold.model import set_resolver  # noqa

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
            type: Optional[str] = "ex:Entity.json"
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
                            "knows": {
                                "@id": "schema:knows",
                                "@type": "@id",
                                "@container": "@set",
                            }
                        },
                    ],
                    "iri": "Person.json",
                }
            )
            type: Optional[str] = "ex:Person.json"
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

    # create a resolver to resolve IRIs to objects
    class SparqlResolver(Resolver):
        # model_config = ConfigDict(
        #    arbitrary_types_allowed=True
        # )
        class Config:
            arbitrary_types_allowed = True

        graph: Graph

        def resolve_iri(self, iri):
            # sparql query to get a node by IRI with all its properties
            # using CONSTRUCT to get the full node
            # format the result as json-ld
            iri_filter = f"FILTER (?s = {iri})"
            # check if the iri is a full IRI or a prefix
            if iri.startswith("http"):
                iri_filter = f"FILTER (?s = <{iri}>)"
            qres = self.graph.query(
                """
                PREFIX ex: <https://example.com/>
                CONSTRUCT {
                    ?s ?p ?o .
                }
                WHERE {
                    ?s ?p ?o .
                    {{{iri_filter}}}
                }
                """.replace(
                    "{{{iri_filter}}}", iri_filter
                )
            )
            jsonld_dict = json.loads(qres.serialize(format="json-ld"))[0]
            res = LinkedBaseModel.from_jsonld(jsonld_dict)
            return res

        def resolve(self, request: ResolveParam):
            # print("RESOLVE", request)
            nodes = {}
            for iri in request.iris:
                nodes[iri] = self.resolve_iri(iri)
            return ResolveResult(nodes=nodes)

    r = SparqlResolver(graph=g)
    set_resolver(SetResolverParam(iri="ex", resolver=r))

    # load bob from the graph
    bob = r.resolve_iri("ex:Bob")
    print(bob)
    # accessing 'knows' will trigger a sparql query
    # to get the full node of Alice from the graph
    print(bob.knows[0].name)
    assert bob.knows[0].name == "Alice"


def test_rdf_export_and_sparql_query():
    _run("v1")
    _run("v2")


if __name__ == "__main__":
    test_rdf_export_and_sparql_query()
