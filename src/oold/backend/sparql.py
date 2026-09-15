import json
from typing import Any

from pydantic import ConfigDict
from rdflib import Graph
from SPARQLWrapper import JSON, JSONLD, SPARQLWrapper

from oold.backend.auth import UserPwdCredential, get_credential
from oold.backend.interface import (
    Backend,
    ComparisonOperator,
    Query,
    QueryParam,
    ResolveParam,
    Resolver,
    ResolveResult,
    StoreResult,
)

WD_INSTANCE_OF = "http://www.wikidata.org/prop/direct/P31"
"""Wikidata's "instance of" - what this module maps to ``@type``."""

DEFAULT_USER_AGENT = "oold-python (https://github.com/OO-LD/oold-python)"
"""Sent with every SPARQL request.

Public endpoints identify clients by user agent and throttle the ones they
cannot attribute: Wikidata answers the SPARQLWrapper default with
``429 Aggressively rate-limiting to 1 req / min``, so a request that looks
correct still fails. Their policy asks for a tool name and a contact URL.
"""


class LocalSparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    graph: Graph | None = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.graph is None:
            self.graph = Graph()

    def query(self, param: QueryParam) -> ResolveResult:
        """Same translation as the remote resolver, run against the local graph.

        Having both go through ``_translate`` is what makes the offline test a
        check on the translation rather than on a second implementation of it.
        """
        model_cls = param.model_cls or self.model_cls
        if model_cls is None:
            raise ValueError("No model_cls provided in request or resolver")
        patterns = _translate(param.query, model_cls, [0])
        rows = self.graph.query("SELECT DISTINCT ?s WHERE {\n" + patterns + "\n}")
        iris = [str(row[0]) for row in rows]
        return self.resolve(ResolveParam(iris=iris, model_cls=model_cls))

    def resolve_iris(self, iris: list[str]) -> dict[str, dict]:
        # sparql query to get a node by IRI with all its properties
        # using CONSTRUCT to get the full node
        # format the result as json-ld
        jsonld_dicts = {}
        for iri in iris:
            iri_filter = f"FILTER (?s = {iri})"
            # check if the iri is a full IRI or a prefix
            if iri.startswith("http"):
                iri_filter = f"FILTER (?s = <{iri}>)"
            # todo: build full iri / prefix mapping from model context
            qres = self.graph.query(_construct_node(iri_filter, "PREFIX ex: <https://example.com/>"))
            jsonld_dict = json.loads(qres.serialize(format="json-ld"))[0]
            jsonld_dicts[iri] = jsonld_dict
        return jsonld_dicts


class LocalSparqlBackend(LocalSparqlResolver, Backend):
    def store_jsonld_dicts(self, jsonld_dicts: dict[str, dict]) -> StoreResult:
        # delete all triples with the given iris as subject
        for iri in jsonld_dicts:
            iri_filter = f"{iri}"
            # check if the iri is a full IRI or a prefix
            if iri.startswith("http"):
                iri_filter = f"<{iri}>"
            query = """
                PREFIX ex: <https://example.com/>
                DELETE WHERE {
                    {{{iri_filter}}} ?p ?o .
                }
                """.replace("{{{iri_filter}}}", iri_filter)
            self.graph.update(query)
            # convert jsonld_dict to rdflib triples and add to graph
            g = Graph()
            g.parse(data=json.dumps(jsonld_dicts[iri]), format="json-ld")
            self.graph += g
        return StoreResult(success=True)


class SparqlResolver(Resolver):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    endpoint: str
    user_agent: str = DEFAULT_USER_AGENT
    query_limit: int = 100
    use_credentials: bool = True
    """Whether to look a stored credential up for this endpoint.

    ``find_credential`` matches by substring, so a public endpoint would send
    any credential whose key happens to be contained in its URL.
    """

    def _prefixes(self) -> str:
        """PREFIX declarations for the generated queries."""
        return "PREFIX ex: <https://example.com/>"

    def _subject_patterns(self, model_cls: Any) -> str:
        """Extra graph patterns constraining ?s. Empty unless a subclass adds any."""
        return ""

    def _post_process(self, jsonld_dict: dict) -> dict:
        """Endpoint-specific rewriting of a fetched document."""
        return jsonld_dict

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._sparql = SPARQLWrapper(self.endpoint, agent=self.user_agent)

    def query(self, param: QueryParam) -> ResolveResult:
        """Find the subjects matching a Condition / Query, then resolve them.

        Only the comparison operators the DSL already builds are translated
        (eq, ne, lt, le, gt, ge) plus ``&``. Anything else raises rather than
        quietly returning the wrong rows.
        """
        model_cls = param.model_cls or self.model_cls
        if model_cls is None:
            raise ValueError("No model_cls provided in request or resolver")
        patterns = self._subject_patterns(model_cls) + _translate(param.query, model_cls, [0])
        self._sparql.setQuery("SELECT DISTINCT ?s WHERE {\n" + patterns + "\n} LIMIT " + str(self.query_limit))
        self._sparql.setReturnFormat(JSON)
        rows = self._sparql.query().convert()["results"]["bindings"]
        iris = [row["s"]["value"] for row in rows]
        return self.resolve(ResolveParam(iris=iris, model_cls=model_cls))

    def resolve_iris(self, iris: list[str]) -> dict[str, dict]:
        # sparql query to get a node by IRI with all its properties
        # using CONSTRUCT to get the full node
        # format the result as json-ld
        jsonld_dicts = {}

        # lookup  credential for the endpoint
        cred = None
        if self.use_credentials:
            try:
                cred = get_credential(self.endpoint)
            except ValueError:
                cred = None
        if cred is not None and isinstance(cred, UserPwdCredential):
            self._sparql.setCredentials(cred.username, cred.password.get_secret_value())

        for iri in iris:
            iri_filter = f"FILTER (?s = {iri})"
            # check if the iri is a full IRI or a prefix
            if iri.startswith("http"):
                iri_filter = f"FILTER (?s = <{iri}>)"
            self._sparql.setQuery(_construct_node(iri_filter, self._prefixes()))
            self._sparql.setReturnFormat(JSONLD)
            result: Graph = self._sparql.query().convert()
            if len(result) == 0:
                jsonld_dicts[iri] = None
                continue
            jsonld_dicts[iri] = self._post_process(json.loads(result.serialize(format="json-ld"))[0])

        return jsonld_dicts


class WikiDataSparqlResolver(SparqlResolver):
    """Wikidata, which differs from a plain SPARQL endpoint in two ways.

    It states class membership with ``wdt:P31`` rather than ``rdf:type``, so that
    is mapped to ``@type`` on the way in and used to constrain queries on the way
    out. Everything else - the user agent, the CONSTRUCT, the DSL translation -
    is the base resolver's.
    """

    endpoint: str = "https://query.wikidata.org/sparql"
    use_credentials: bool = False  # public endpoint; never send stored secrets

    def _prefixes(self) -> str:
        return "PREFIX ex: <https://example.com/>\nPREFIX Item: <http://www.wikidata.org/entity/>"

    def _subject_patterns(self, model_cls: Any) -> str:
        # A label matches far more than one kind of thing - "Tim Berners-Lee" is
        # also a book edition - and resolving those fails on an unknown type IRI.
        class_iri = next((iri for iri in _as_list(model_cls.get_cls_iri()) if str(iri).startswith("http")), None)
        if not class_iri:
            return ""
        return f"    ?s <{WD_INSTANCE_OF}> <{class_iri}> .\n"

    def _post_process(self, jsonld_dict: dict) -> dict:
        if WD_INSTANCE_OF in jsonld_dict:
            jsonld_dict["@type"] = jsonld_dict.pop(WD_INSTANCE_OF)[0]["@id"]
        return jsonld_dict


_SPARQL_OPERATORS = {
    ComparisonOperator.EQ: "=",
    ComparisonOperator.NE: "!=",
    ComparisonOperator.LT: "<",
    ComparisonOperator.LE: "<=",
    ComparisonOperator.GT: ">",
    ComparisonOperator.GE: ">=",
}


def _construct_node(iri_filter: str, prefixes: str = "") -> str:
    """CONSTRUCT every triple of one subject. Shared by all three resolvers."""
    return f"""
        {prefixes}
        CONSTRUCT {{ ?s ?p ?o . }}
        WHERE {{
            ?s ?p ?o .
            {iri_filter}
        }}
    """


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _expand_term(model_cls, field: str, value) -> tuple[str, str]:
    """Return (predicate IRI, SPARQL literal) for a field of ``model_cls``.

    Both come from expanding a probe document against the model's own JSON-LD
    context, so the term definition decides the predicate *and* the literal form
    - a term scoped to ``@language: en`` yields ``"x"@en``, one with an
    ``@type`` yields ``"x"^^<datatype>``. Re-deriving either by hand would be a
    second, divergent reading of the context.
    """
    from pydantic import BaseModel as _BaseModel
    from pyld import jsonld as _jsonld

    from oold.static import build_context, get_jsonld_context_loader

    context = build_context(model_cls, _BaseModel)
    _jsonld.set_document_loader(get_jsonld_context_loader(model_cls, _BaseModel))
    expanded = _jsonld.expand({"@context": context, field: value})
    if not expanded:
        raise ValueError(f"{model_cls.__name__}.{field} is not mapped by the model context")
    node = expanded[0]
    predicate = next((key for key in node if not key.startswith("@")), None)
    if predicate is None:
        raise ValueError(f"{model_cls.__name__}.{field} is not mapped by the model context")
    entry = node[predicate][0]
    if "@id" in entry:
        return predicate, f"<{entry['@id']}>"
    literal = json.dumps(str(entry["@value"]))
    if entry.get("@language"):
        return predicate, f"{literal}@{entry['@language']}"
    if entry.get("@type"):
        return predicate, f"{literal}^^<{entry['@type']}>"
    if isinstance(value, (bool, int, float)):
        return predicate, json.dumps(value)
    return predicate, literal


def _translate(node, model_cls, counter: list[int]) -> str:
    """Render a Condition or Query as SPARQL graph patterns."""
    if isinstance(node, Query):
        if node.operator != "and":
            raise NotImplementedError(f"Unsupported query operator: {node.operator}")
        return _translate(node.op1, model_cls, counter) + "\n" + _translate(node.op2, model_cls, counter)
    predicate, literal = _expand_term(model_cls, node.field, node.value)
    operator = node.operator or ComparisonOperator.EQ
    if operator == ComparisonOperator.EQ:
        # a plain pattern is both selective and index-friendly
        return f"    ?s <{predicate}> {literal} ."
    counter[0] += 1
    var = f"?v{counter[0]}"
    return f"    ?s <{predicate}> {var} .\n    FILTER({var} {_SPARQL_OPERATORS[operator]} {literal})"
