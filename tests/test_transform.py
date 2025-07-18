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
