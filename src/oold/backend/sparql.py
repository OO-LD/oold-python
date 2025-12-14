import json
from typing import Dict, List, Optional

from pydantic import ConfigDict
from rdflib import Graph
from SPARQLWrapper import JSONLD, SPARQLWrapper

from oold.backend.auth import GetCredentialParam, UserPwdCredential, get_credential
from oold.backend.interface import Backend, Resolver, StoreResult


class LocalSparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    graph: Optional[Graph] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.graph is None:
            self.graph = Graph()

    def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
        # sparql query to get a node by IRI with all its properties
        # using CONSTRUCT to get the full node
        # format the result as json-ld
        jsonld_dicts = {}
        for iri in iris:
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
            jsonld_dicts[iri] = jsonld_dict
        return jsonld_dicts


class LocalSparqlBackend(LocalSparqlResolver, Backend):
    def store_jsonld_dicts(self, jsonld_dicts: Dict[str, Dict]) -> StoreResult:
        # delete all triples with the given iris as subject
        for iri in jsonld_dicts.keys():
            iri_filter = f"{iri}"
            # check if the iri is a full IRI or a prefix
            if iri.startswith("http"):
                iri_filter = f"<{iri}>"
            query = """
                PREFIX ex: <https://example.com/>
                DELETE WHERE {
                    {{{iri_filter}}} ?p ?o .
                }
                """.replace(
                "{{{iri_filter}}}", iri_filter
            )
            self.graph.update(query)
            # convert jsonld_dict to rdflib triples and add to graph
            g = Graph()
            g.parse(data=json.dumps(jsonld_dicts[iri]), format="json-ld")
            self.graph += g
        return StoreResult(success=True)

    def query():
        raise NotImplementedError()


class SparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    endpoint: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._sparql = SPARQLWrapper(self.endpoint)

    def resolve_iris(self, iris: List[str]) -> Dict[str, Dict]:
        # sparql query to get a node by IRI with all its properties
        # using CONSTRUCT to get the full node
        # format the result as json-ld
        jsonld_dicts = {}

        # lookup  credential for the endpoint
        cred = get_credential(GetCredentialParam(iri=self.endpoint))
        if cred is not None:
            if isinstance(cred, UserPwdCredential):
                self._sparql.setCredentials(
                    cred.username, cred.password.get_secret_value()
                )

        for iri in iris:
            iri_filter = f"FILTER (?s = {iri})"
            # check if the iri is a full IRI or a prefix
            if iri.startswith("http"):
                iri_filter = f"FILTER (?s = <{iri}>)"
            self._sparql.setQuery(
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
            self._sparql.setReturnFormat(JSONLD)
            result: Graph = self._sparql.query().convert()
            if len(result) == 0:
                jsonld_dicts[iri] = None
                continue
            jsonld_dict = json.loads(result.serialize(format="json-ld"))[0]
            jsonld_dicts[iri] = jsonld_dict

        return jsonld_dicts


class WikiDataSparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    endpoint: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._sparql = SPARQLWrapper(self.endpoint)

    def resolve_iri(self, iris: List[str]) -> Dict[str, Dict]:
        # sparql query to get a node by IRI with all its properties
        # using CONSTRUCT to get the full node
        # format the result as json-ld
        jsonld_dicts = {}
        for iri in iris:
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
            jsonld_dicts[iri] = jsonld_dict

        return jsonld_dicts
