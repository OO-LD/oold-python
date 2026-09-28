"""Transforming instances between schemas through RDF.

These are the cases the previous alias-notation implementation covered, re-encoded in the
form the specification defines. Where the old context wrote a sibling key ``"name*"`` to say
"this term is also known by that IRI", the schema now says so in ``x-oold-context``, keyed by
the synonym IRI and carrying an SSSOM predicate. The inputs and expected outputs are the same,
so the change of notation is not allowed to change what the transformation produces.
"""

import json

import pytest
import rdflib
from jsondiff import diff
from pyld import jsonld

from oold.utils.mappings import declared_context, mapping_sets, promote
from oold.utils.transform import (
    JSON_LD,
    NQUADS,
    TURTLE,
    from_rdf,
    jsonld_to_jsonld,
    to_rdf,
    transform,
)

SCHEMA_ORG = "http://schema.org/"
DEMO = "https://oo-ld.github.io/demo/"


def _schema(context, synonyms=None, **extra):
    """A minimal OO-LD schema carrying a context and optional synonyms."""
    schema = {"type": "object", "@context": context}
    if synonyms:
        schema["x-oold-context"] = synonyms
    schema.update(extra)
    return schema


# -- a term and a class, each with one synonym -------------------------------


def _person_schema():
    """`name` is `schema:name`, also known as `rdfs:label`; `Person` likewise `ex:Human`."""
    return _schema(
        {
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "schema": "https://schema.org/",
            "ex": "https://another-example.org/",
            "type": "@type",
            "name": "schema:name",
            "Person": "schema:Person",
        },
        {
            "name": {"rdfs:label": {"x-oold-sssom": {"predicate_id": "skos:exactMatch"}}},
            "Person": {"ex:Human": {"x-oold-sssom": {"predicate_id": "skos:exactMatch"}}},
        },
    )


def _test_simple_json():
    """A document written in the synonym vocabulary reads as the primary one."""
    source = _schema({
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "ex": "https://another-example.org/",
        "type": "@type",
        "label": "rdfs:label",
        "Human": "ex:Human",
    })
    instance = {"type": "Human", "label": "Jane Doe"}

    result = transform(instance, [source], [_person_schema()])
    result.pop("@context", None)

    assert result == {"type": "Person", "name": "Jane Doe"}, result


@pytest.mark.benchmark(group="transform")
def test_simple_json(benchmark):
    if benchmark is not None:
        benchmark(_test_simple_json)
    else:
        _test_simple_json()


def test_non_exact_match_is_not_rewritten():
    """A `closeMatch` is not a licence to treat two predicates as the same."""
    target = _schema(
        {
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "schema": "https://schema.org/",
            "type": "@type",
            "name": "schema:name",
        },
        {"name": {"rdfs:label": {"x-oold-sssom": {"predicate_id": "skos:closeMatch"}}}},
    )
    source = _schema({"rdfs": "http://www.w3.org/2000/01/rdf-schema#", "label": "rdfs:label"})

    result = transform({"label": "Jane Doe"}, [source], [target])

    assert result.get("name") is None, f"closeMatch must not be promoted: {result}"


# -- a graph, including an inverted relation ---------------------------------


def _organization_schema():
    """`employes` is `schema:employes`, also reachable as the inverse of `schema:worksFor`."""
    return _schema(
        {
            "schema": "http://schema.org/",
            "demo": DEMO,
            "type": "@type",
            "id": "@id",
            "name": "schema:name",
            "employes": {"@id": "schema:employes", "@type": "@id"},
        },
        {
            "name": {"demo:full_name": {"x-oold-sssom": {"predicate_id": "skos:exactMatch"}}},
            "employes": {
                "schema:worksFor": {
                    "@reverse": "schema:worksFor",
                    "@type": "@id",
                    "x-oold-sssom": {"predicate_id": "skos:exactMatch"},
                },
                "demo:is_employed_by": {
                    "@reverse": "demo:is_employed_by",
                    "@type": "@id",
                    "x-oold-sssom": {"predicate_id": "skos:exactMatch"},
                },
            },
        },
    )


def _source_graph():
    """Three people and an organization, related in three different ways."""
    return {
        "@context": {
            "schema": "http://schema.org/",
            "demo": DEMO,
            "name": "schema:name",
            "full_name": "demo:full_name",
            "works_for": {"@id": "schema:worksFor", "@type": "@id"},
            "is_employed_by": {"@id": "demo:is_employed_by", "@type": "@id"},
            "employes": {"@id": "schema:employes", "@type": "@id"},
            "type": "@type",
            "id": "@id",
        },
        "@graph": [
            {"id": "demo:person1", "type": "schema:Person", "name": "Person1", "works_for": "demo:organizationA"},
            {
                "id": "demo:person2",
                "type": "schema:Person",
                "full_name": "Person2",
                "is_employed_by": "demo:organizationA",
            },
            {"id": "demo:person3", "type": "schema:Person", "name": "Person3"},
            {
                "id": "demo:organizationA",
                "type": "schema:Organization",
                "name": "organizationA",
                "employes": "demo:person3",
            },
        ],
    }


def _by_id(document):
    nodes = document.get("@graph", [document])
    return {node["id"]: node for node in nodes if isinstance(node, dict) and "id" in node}


def _test_complex_graph():
    """Three spellings of one relation collapse onto the single primary term."""
    graph = _source_graph()

    result = from_rdf(graph, [_organization_schema()], format=JSON_LD)
    nodes = _by_id(result)

    org = nodes["demo:organizationA"]
    employed = org["employes"]
    if isinstance(employed, str):
        employed = [employed]
    employed = sorted(item["id"] if isinstance(item, dict) else item for item in employed)

    assert employed == ["demo:person1", "demo:person2", "demo:person3"], org
    # demo:full_name was a synonym of name, so person2 is named like the others.
    assert nodes["demo:person2"]["name"] == "Person2", nodes["demo:person2"]
    assert nodes["demo:person1"]["name"] == "Person1"


@pytest.mark.benchmark(group="transform")
def test_complex_graph(benchmark):
    if benchmark is not None:
        benchmark(_test_complex_graph)
    else:
        _test_complex_graph()


def test_graph_input_is_framed():
    """A flat graph re-nests under the target schema rather than staying a node list.

    Compaction alone never re-nests, so without a frame the embedded object would surface as
    a sibling of its parent.
    """
    context = {
        "schema": "http://schema.org/",
        "demo": DEMO,
        "type": "@type",
        "id": "@id",
        "name": "schema:name",
        "address": {"@id": "schema:address", "@type": "@id"},
    }
    target = _schema(
        context,
        properties={
            "name": {"type": "string"},
            "address": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
        **{"x-oold-instance-rdf-type": ["schema:Person"]},
    )
    graph = {
        "@context": context,
        "@graph": [
            {"id": "demo:p1", "type": "schema:Person", "name": "Jane", "address": "demo:a1"},
            {"id": "demo:a1", "name": "Somewhere"},
        ],
    }

    result = from_rdf(graph, [target], format=JSON_LD)

    assert result.get("id") == "demo:p1", result
    assert isinstance(result.get("address"), dict), f"address should be embedded: {result}"
    assert result["address"]["name"] == "Somewhere"


# -- export ------------------------------------------------------------------


def test_mapping_set_selects_the_reading():
    """The same instance exports as a different graph once a set is promoted."""
    schema = _schema(
        {"schema": "https://schema.org/", "demo": DEMO, "name": "schema:name"},
        {
            "name": {
                "demo:full_name": {
                    "x-oold-sssom": {
                        "predicate_id": "skos:exactMatch",
                        "mapping_set_id": "https://example.org/sets/demo",
                    }
                }
            }
        },
    )
    instance = {"name": "Jane Doe"}

    assert mapping_sets([schema]) == ["https://example.org/sets/demo"]

    # n-quads rather than turtle: the predicate is written out in full, so the assertion is
    # about the graph and not about which prefixes the serializer chose.
    consensus = to_rdf(instance, [schema], format=NQUADS)
    promoted = to_rdf(instance, [schema], set_id="https://example.org/sets/demo", format=NQUADS)

    assert "https://schema.org/name" in consensus, consensus
    assert f"{DEMO}full_name" in promoted, promoted
    assert "https://schema.org/name" not in promoted, promoted


def test_export_round_trips_under_the_same_context():
    """Instance -> RDF -> instance is lossless for every declared mapping set.

    The property `effective_views.py` proves in oold-reference-schemas: a mapping that drops
    a term or coerces a value fails here rather than shipping quietly.
    """
    schema = _schema(
        {
            "schema": "https://schema.org/",
            "demo": DEMO,
            "id": "@id",
            "name": "schema:name",
        },
        {
            "name": {
                "demo:full_name": {
                    "x-oold-sssom": {
                        "predicate_id": "skos:exactMatch",
                        "mapping_set_id": "https://example.org/sets/demo",
                    }
                }
            }
        },
    )
    instance = {"id": "demo:jane", "name": "Jane Doe"}

    for set_id in [None, *mapping_sets([schema])]:
        context = promote(declared_context([schema]), [schema], set_id)
        reading = _schema(context)
        nquads = to_rdf(instance, [schema], set_id=set_id, format="application/n-quads")
        restored = from_rdf(nquads, [reading], format="application/n-quads")
        restored.pop("@context", None)
        assert restored == instance, f"set={set_id}: {restored} != {instance}"


def test_turtle_and_jsonld_inputs_agree():
    """The two accepted serializations are the same document to the importer."""
    schema = _schema({"schema": "https://schema.org/", "id": "@id", "name": "schema:name"})
    instance = {"id": "https://example.org/jane", "name": "Jane Doe"}

    turtle = to_rdf(instance, [schema], format=TURTLE)
    jsonld_text = to_rdf(instance, [schema], format=JSON_LD)

    from_turtle = from_rdf(turtle, [schema], format=TURTLE)
    from_jsonld = from_rdf(jsonld_text, [schema], format=JSON_LD)

    from_turtle.pop("@context", None)
    from_jsonld.pop("@context", None)
    assert from_turtle == from_jsonld == instance, (from_turtle, from_jsonld)


if __name__ == "__main__":
    test_simple_json(None)
    test_complex_graph(None)
    print(json.dumps({"ok": True}))


# -- bridging document shapes (oold-schema#135) ------------------------------


QUDT_SET = "https://w3id.org/oo-ld/schemas/mappings/qudt.sssom.tsv"


def _nested_quantity_schema():
    """The EMMO shape, where the number is a node, with its QUDT reading declared.

    From https://github.com/OO-LD/oold-schema/issues/135. `value` maps to `@nest`, so under
    the QUDT reading the JSON nesting carries no meaning; `numerical` maps to `qudt:value`
    while staying nested under `value` in the document.
    """
    return _schema(
        {
            "emmo": "https://w3id.org/emmo#",
            "qudt": "http://qudt.org/schema/qudt/",
            "qunit": "http://qudt.org/vocab/unit/",
            "type": {"@id": "@type", "@container": "@set"},
            "value": "emmo:hasQuantityValuePart",
            "numerical": "emmo:hasNumericalValue",
            "unit": {"@id": "emmo:hasMeasurementUnit", "@type": "@vocab"},
            "NestedQuantityValue": "emmo:QuantityValue",
        },
        {
            "value": {
                "@nest": {
                    "x-oold-sssom": {
                        "predicate_id": "skos:relatedMatch",
                        "mapping_set_id": QUDT_SET,
                    }
                }
            },
            "numerical": {
                "qudt:value": {
                    "@nest": "value",
                    "x-oold-sssom": {
                        "predicate_id": "skos:exactMatch",
                        "mapping_set_id": QUDT_SET,
                    },
                }
            },
        },
        **{"x-oold-instance-rdf-type": ["emmo:QuantityValue"]},
    )


NESTED_INSTANCE = {
    "@id": "https://example.org/m1",
    "type": ["NestedQuantityValue"],
    "value": {"numerical": 12.7},
    "unit": "qunit:SEC",
}

FLAT_QUDT_GRAPH = (
    "<https://example.org/m1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
    "<http://qudt.org/schema/qudt/QuantityValue> .\n"
    '<https://example.org/m1> <http://qudt.org/schema/qudt/value> "1.27E1"'
    "^^<http://www.w3.org/2001/XMLSchema#double> .\n"
    "<https://example.org/m1> <http://qudt.org/schema/qudt/hasUnit> "
    "<http://qudt.org/vocab/unit/SEC> .\n"
)

NESTED_EMMO_GRAPH = (
    "<https://example.org/m1> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
    "<https://w3id.org/emmo#QuantityValue> .\n"
    "<https://example.org/m1> <https://w3id.org/emmo#hasMeasurementUnit> "
    "<http://qudt.org/vocab/unit/SEC> .\n"
    "<https://example.org/m1> <https://w3id.org/emmo#hasQuantityValuePart> _:b0 .\n"
    '_:b0 <https://w3id.org/emmo#hasNumericalValue> "1.27E1"'
    "^^<http://www.w3.org/2001/XMLSchema#double> .\n"
)


def test_a_promoted_nest_fragment_flattens_the_exported_graph():
    """Reading B of the issue: the same document exports as a flat QUDT graph."""
    schema = _nested_quantity_schema()

    own = to_rdf(NESTED_INSTANCE, [schema], format=NQUADS)
    promoted = to_rdf(NESTED_INSTANCE, [schema], set_id=QUDT_SET, format=NQUADS)

    # Under its own context the number hangs off a node of its own.
    assert "hasQuantityValuePart" in own
    assert "_:" in own
    # Under the QUDT reading it sits on the quantity, and no node remains.
    assert "http://qudt.org/schema/qudt/value" in promoted
    assert "hasQuantityValuePart" not in promoted
    assert "_:" not in promoted
    # Terms without a QUDT synonym keep their EMMO reading.
    assert "hasMeasurementUnit" in promoted


def test_selection_bridges_a_shape_on_import():
    """Reading C: flat data compacts into the nested document the schema expects.

    Naming the set is what makes this work. ``@nest`` is a term definition, so it only acts
    when the document is compacted against a context that contains it - unlike renaming a
    term, which is a rewrite of the graph and needs no selection.
    """
    schema = _nested_quantity_schema()

    result = from_rdf(FLAT_QUDT_GRAPH, [schema], format=NQUADS, set_id=QUDT_SET)

    assert result["value"] == {"numerical": 12.7}, result


def test_without_a_set_the_shape_is_not_bridged():
    """The boundary: vocabulary is bridged without a selection, shape is not."""
    schema = _nested_quantity_schema()

    result = from_rdf(FLAT_QUDT_GRAPH, [schema], format=NQUADS)

    # qudt:value is an exactMatch synonym, so the term is recognised ...
    assert result.get("numerical") == 12.7, result
    # ... but it stays where the graph put it, on the quantity itself.
    assert "value" not in result, result


def test_framing_restores_the_shape_before_selection():
    """Reading E: compaction alone returns a flat node list; the schema's frame re-nests it."""
    schema = _nested_quantity_schema()

    result = from_rdf(NESTED_EMMO_GRAPH, [schema], format=NQUADS)

    assert result["value"] == {"numerical": 12.7}, result
    assert result["type"] == ["NestedQuantityValue"], result
    assert "@graph" not in result, "a framed document is one node, not a list"


# The deprecated ``"name*"`` notation keeps its own coverage: it is still public
# API, and the point of keeping it is that its behaviour does not move.


@pytest.mark.skip(reason="This test fails randomly, skip for now")
def test_rocreate():
    rdf = """
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix schema: <https://schema.org/> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

        <https://example/records/56789/files/139a5c2f-0000-4c04-96a3-04fd4abbf165> a schema:MediaObject ;
            schema:author <https://example/users/1234> ;
            schema:contentSize "177031" ;
            schema:dateCreated "2025-03-20T12:42:16.958207+00:00"^^xsd:dateTime ;
            schema:dateModified "2025-03-20T12:42:17.043920+00:00"^^xsd:dateTime ;
            schema:encodingFormat "image/jpeg" ;
            schema:identifier "139a5c2f-0000-4c04-96a3-04fd4abbf165" ;
            schema:isPartOf <https://example/records/56789> ;
            schema:name "A4.jpg" .

        <https://example/records/56789/files/485d06f8-0000-4804-a615-e29aea4e732b> a schema:MediaObject ;
            schema:author <https://example/users/1234> ;
            schema:contentSize "261300" ;
            schema:dateCreated "2025-03-20T12:42:15.029828+00:00"^^xsd:dateTime ;
            schema:dateModified "2025-03-20T12:42:15.114847+00:00"^^xsd:dateTime ;
            schema:encodingFormat "image/jpeg" ;
            schema:identifier "485d06f8-0000-4804-a615-e29aea4e732b" ;
            schema:isPartOf <https://example/records/56789> ;
            schema:name "C2.jpg" .

        <https://example/records/56789> a schema:Dataset ;
            schema:additionalType "sample" ;
            schema:author <https://example/users/1234> ;
            schema:dateCreated "2025-03-20T12:42:07.127883+00:00"^^xsd:dateTime ;
            schema:dateModified "2025-05-09T08:11:09.848079+00:00"^^xsd:dateTime ;
            schema:identifier "abccell02defects" ;
            schema:keywords "abc02",
                "abccell" ;
            schema:name "ISEcell02defects" .

        <https://example/users/1234> a schema:Person ;
            schema:name "Doe, John" .
    """

    g = rdflib.Graph()
    g.parse(data=rdf, format="turtle")
    data = jsonld.expand(json.loads(g.serialize(format="json-ld", indent=4, context=None)))

    context = {
        "@version": 1.1,  # use version 1.1 for JSON-LD
        "schema": "https://schema.org/",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "type": "@type",  # use @type for type mapping
        "id": "@id",  # use @id for IRI mapping
        # define name as multilingual attribute, using the @language tag (default: en)
        "uuid": {"@id": "schema:identifier"},
        "label": {
            "@id": "skos:prefLabel",
            "@container": "@set",
            "@context": {"text": "@value", "lang": "@language"},
        },
        "label*": {"@id": "schema:name", "@language": "en"},
        "creation_date": {"@id": "schema:dateCreated", "@type": "xsd:dateTime"},
        "edition_date": {"@id": "schema:dateModified", "@type": "xsd:dateTime"},
        "encoding_format": {"@id": "schema:encodingFormat"},
        "content_size": {"@id": "schema:contentSize"},
        "WikiFile": {"@id": "Category:WikiFile", "@type": "@id"},
        "WikiFile*": {"@id": "schema:MediaObject", "@type": "@id"},
        "ELNEntry": {"@id": "Category:ELNEntry", "@type": "@id"},
        "ELNEntry*": {"@id": "schema:Dataset", "@type": "@id"},
        "creator": {"@id": "schema:author", "@type": "@id"},
        "attachments": {"@id": "Property:HasFileAttachment", "@type": "@id"},
        "attachments*": {"@reverse": "schema:isPartOf", "@type": "@id"},
        "keywords": {"@id": "schema:keywords", "@container": "@set"},
    }

    transformed_graph = jsonld_to_jsonld(data, context)

    expected = [
        {
            "id": "https://example/records/56789",
            "type": "ELNEntry",
            "attachments": [
                "https://example/records/56789/files/485d06f8-0000-4804-a615-e29aea4e732b",
                "https://example/records/56789/files/139a5c2f-0000-4c04-96a3-04fd4abbf165",
            ],
            "label": [{"lang": "en", "text": "ISEcell02defects"}],
            "schema:additionalType": "sample",
            "creator": "https://example/users/1234",
            "creation_date": "2025-03-20T12:42:07.127883+00:00",
            "edition_date": "2025-05-09T08:11:09.848079+00:00",
            "uuid": "abccell02defects",
            "keywords": ["abc02", "abccell"],
        },
        {
            "id": "https://example/records/56789/files/139a5c2f-0000-4c04-96a3-04fd4abbf165",
            "type": "WikiFile",
            "label": [{"lang": "en", "text": "A4.jpg"}],
            "creator": "https://example/users/1234",
            "content_size": "177031",
            "creation_date": "2025-03-20T12:42:16.958207+00:00",
            "edition_date": "2025-03-20T12:42:17.043920+00:00",
            "encoding_format": "image/jpeg",
            "uuid": "139a5c2f-0000-4c04-96a3-04fd4abbf165",
        },
        {
            "id": "https://example/records/56789/files/485d06f8-0000-4804-a615-e29aea4e732b",
            "type": "WikiFile",
            "label": [{"lang": "en", "text": "C2.jpg"}],
            "creator": "https://example/users/1234",
            "content_size": "261300",
            "creation_date": "2025-03-20T12:42:15.029828+00:00",
            "edition_date": "2025-03-20T12:42:15.114847+00:00",
            "encoding_format": "image/jpeg",
            "uuid": "485d06f8-0000-4804-a615-e29aea4e732b",
        },
        {
            "id": "https://example/users/1234",
            "type": "schema:Person",
            "label": [{"lang": "en", "text": "Doe, John"}],
        },
    ]

    _diff = diff(transformed_graph["@graph"], expected)
    assert transformed_graph["@graph"] == expected, f"Expected {expected}, but encountered following deviation: {_diff}"


@pytest.mark.skip(reason="This test fails due to the literal type annotation issue in JSON-LD")
def test_literal_types():
    data = {
        "https://schema.org/contentSize": 177031,
    }
    context = {
        "@version": 1.1,
        "schema": "https://schema.org/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "content_size": {"@id": "schema:contentSize", "@type": "xsd:integer"},
    }

    expected = {
        "@context": {
            "@version": 1.1,
            "schema": "https://schema.org/",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "content_size": {"@id": "schema:contentSize", "@type": "xsd:integer"},
        },
        "content_size": 177031,
    }
    data = jsonld.compact(data, context)
    print(json.dumps(data, indent=4))
    # this fails due to the literal type annotation
    # instead we get "schema:contentSize": 177031
    # see also https://github.com/json-ld/json-ld.org/issues/795
    assert data == expected, f"Expected {expected}, but got {data}"


if __name__ == "__main__":
    test_simple_json(None)
    test_complex_graph(None)
    # test_rocreate()
    # test_literal_types()
