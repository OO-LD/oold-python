import json

import pytest
import rdflib
from jsondiff import diff
from pyld import jsonld

from oold.utils.transform import json_to_json, jsonld_to_jsonld


def test_simple_json():
    input_data = {"type": "Human", "label": "Jane Doe"}

    input_context = {
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "label": "rdfs:label",
        "type": "@type",
        "ex": "https://another-example.org/",
        "Human": "ex:Human",
    }
    mapping_context = {
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "schema": "https://schema.org/",
        "name*": "rdfs:label",
        "name": "schema:name",
        "type": "@type",
        "ex": "https://another-example.org/",
        "Person*": "ex:Human",
        "Person": "schema:Person",
    }
    output_data = json_to_json(input_data, mapping_context, input_context)
    expected_output_data = {
        "type": "Person",
        "name": "Jane Doe",
    }

    print("Output Data:", output_data)
    assert (
        output_data == expected_output_data
    ), f"Expected {expected_output_data}, but got {output_data}"


def test_complex_graph():
    graph = {
        "@context": {
            "schema": "http://schema.org/",
            "demo": "https://oo-ld.github.io/demo/",
            "name": "schema:name",
            "full_name": "demo:full_name",
            "label": "demo:label",
            "works_for": {"@id": "schema:worksFor", "@type": "@id"},
            "is_employed_by": {"@id": "demo:is_employed_by", "@type": "@id"},
            "employes": {"@id": "schema:employes", "@type": "@id"},
            "type": "@type",
            "id": "@id",
        },
        "@graph": [
            {
                "id": "demo:person1",
                "type": "schema:Person",
                "name": "Person1",
                "works_for": "demo:organizationA",
            },
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
                "label": "organizationA",
                "employes": "demo:person3",
            },
        ],
    }
    # graph["@graph"] = sorted(graph["@graph"], key=lambda x: x['@id'])

    context = {
        "schema": "http://schema.org/",
        "demo": "https://oo-ld.github.io/demo/",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "name": "schema:name",
        "name*": "demo:full_name",
        # "_demo_full_name": "demo:full_name", # generated
        ##"label": {"@id": "skos:prefLabel", "@container": "@set", "@language": "en", "@context": {"text": "@value", "lang": "@language"}},  # noqa
        "text": "@value",
        "lang": "@language",
        "label": {"@id": "skos:prefLabel", "@container": "@set"},
        "label*": {"@id": "demo:label", "@container": "@set", "@language": "en"},
        # "_demo_label": {"@id": "demo:label"},#, "@container": "@set", "@language": "en"}, # generated  # noqa
        "employes": {"@id": "schema:employes", "@type": "@id"},
        "employes*": {"@reverse": "schema:worksFor", "@type": "@id"},
        # "_schema_worksFor": {"@id": "schema:worksFor", "@type": "@id"}, # generated
        "employes**": {"@reverse": "demo:is_employed_by", "@type": "@id"},
        # "_demo_is_employed_by": {"@id": "demo:is_employed_by", "@type": "@id"}, # generated  # noqa
        "type": "@type",
        "id": "@id",
    }

    transformed_graph = jsonld_to_jsonld(graph, context)
    # print("Transformed Graph:", json.dumps(transformed_graph, indent=2))

    expected = {
        "@context": {
            "demo": "https://oo-ld.github.io/demo/",
            "employes": {"@id": "schema:employes", "@type": "@id"},
            "employes*": {"@reverse": "schema:worksFor", "@type": "@id"},
            "employes**": {"@reverse": "demo:is_employed_by", "@type": "@id"},
            "id": "@id",
            "label": {"@container": "@set", "@id": "skos:prefLabel"},
            "label*": {"@container": "@set", "@id": "demo:label", "@language": "en"},
            "lang": "@language",
            "name": "schema:name",
            "name*": "demo:full_name",
            "schema": "http://schema.org/",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "text": "@value",
            "type": "@type",
        },
        "@graph": [
            {
                "employes": ["demo:person1", "demo:person2", "demo:person3"],
                "id": "demo:organizationA",
                "label": [{"lang": "en", "text": "organizationA"}],
                "type": "schema:Organization",
            },
            {"id": "demo:person1", "name": "Person1", "type": "schema:Person"},
            {"id": "demo:person2", "name": "Person2", "type": "schema:Person"},
            {"id": "demo:person3", "name": "Person3", "type": "schema:Person"},
        ],
    }

    # from jsondiff import diff
    # _diff = json.dumps(diff(transformed_graph, expected), indent=2)
    # assert transformed_graph == expected,
    # f"Expected {expected}, but encountered following deviation: {_diff}"

    assert (
        transformed_graph == expected
    ), f"Expected {expected}, but got {transformed_graph}"


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
    """  # noqa

    g = rdflib.Graph()
    g.parse(data=rdf, format="turtle")
    data = jsonld.expand(
        json.loads(g.serialize(format="json-ld", indent=4, context=None))
    )

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
                "https://example/records/56789/files/485d06f8-0000-4804-a615-e29aea4e732b",  # noqa
                "https://example/records/56789/files/139a5c2f-0000-4c04-96a3-04fd4abbf165",  # noqa
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
            "id": "https://example/records/56789/files/139a5c2f-0000-4c04-96a3-04fd4abbf165",  # noqa
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
            "id": "https://example/records/56789/files/485d06f8-0000-4804-a615-e29aea4e732b",  # noqa
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
    assert (
        transformed_graph["@graph"] == expected
    ), f"Expected {expected}, but encountered following deviation: {_diff}"


@pytest.mark.skip(
    reason="This test fails due to the literal type annotation issue in JSON-LD"
)
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
    test_simple_json()
    test_complex_graph()
    test_rocreate()
    test_literal_types()
