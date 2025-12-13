import json
from typing import Dict, Optional

from pydantic import ConfigDict
from rdflib import Graph
from SPARQLWrapper import JSONLD, SPARQLWrapper

from oold.backend.interface import Resolver


class LocalSparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    graph: Optional[Graph] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.graph is None:
            self.graph = Graph()

    def resolve_iri(self, iri) -> Dict:
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
        return jsonld_dict


class WikiDataSparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    endpoint: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._sparql = SPARQLWrapper(self.endpoint)

    def resolve_iri(self, iri):
        # sparql query to get a node by IRI with all its properties
        # using CONSTRUCT to get the full node
        # format the result as json-ld
        iri_filter = f"FILTER (?s = {iri})"
        # check if the iri is a full IRI or a prefix
        if iri.startswith("http"):
            iri_filter = f"FILTER (?s = <{iri}>)"
        self._sparql.setQuery(
            """
            PREFIX ex: <https://example.com/>
            PREFIX Item: <http://www.wikidata.org/entity/>
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
        self._sparql.setReturnFormat(JSONLD)
        result: Graph = self._sparql.query().convert()
        jsonld_dict = json.loads(result.serialize(format="json-ld"))[0]
        # replace http://www.wikidata.org/prop/direct/P31 with @type
        if "http://www.wikidata.org/prop/direct/P31" in jsonld_dict:
            jsonld_dict["@type"] = jsonld_dict.pop(
                "http://www.wikidata.org/prop/direct/P31"
            )[0]["@id"]

        return jsonld_dict
