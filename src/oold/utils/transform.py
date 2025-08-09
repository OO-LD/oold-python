import json

from pyld import jsonld


def jsonld_to_jsonld(graph: dict, transformation_context: dict) -> dict:
    """Applies OO-LD alias notation to transform JSON(-LD) documents

    Parameters
    ----------
    graph
        input JSON(-LD) document to transform
    context
        transformation context, which contains the mapping of aliases to URIs

    Returns
    -------
        transformed JSON(-LD) document
    """
    temp1 = {}
    temp2 = {}
    temp3 = {}

    # # not expanded => at least one key is not an IRI
    # expanded = True

    # if "@context" in graph: expanded = False
    # elif "@graph" in graph:
    #     for item in graph["@graph"]:
    #         if not is_iri(item):
    #             expanded = False
    #             break
    # else:
    #     for key in graph.keys():
    #         if not (":" in value):
    #             expanded = False
    #             break

    # if not context is given, we assume the default context
    # if '@context' not in graph:
    #    graph["@context"] = context

    # in case graph is not expanded we expand first
    # graph = jsonld.expand(graph)

    for key, value in transformation_context.items():
        if key.endswith("*"):
            temp1_value = {}
            temp2_value = {}
            if type(value) is dict:
                if "@id" in value:
                    temp1_value["@id"] = value["@id"]
                if "@reverse" in value:
                    temp1_value["@id"] = value["@reverse"]
                if "@type" in value:
                    temp1_value["@type"] = value["@type"]
                temp2_value = {**value}
                # if "@id" in value: del temp2_value["@id"]
                # if "@reverse" in value: del temp2_value["@reverse"]
            else:
                temp1_value["@id"] = value
                temp2_value["@id"] = value

            org_key = key.replace("*", "")
            org_value = transformation_context[org_key]
            if type(org_value) is dict:
                if "@id" in org_value:
                    # temp2_value["@id"] = org_value["@id"]
                    if "@id" in temp2_value:
                        temp2_value["@id"] = org_value["@id"]
                    if "@reverse" in temp2_value:
                        temp2_value["@reverse"] = org_value["@id"]
                # if "@reverse" in org_value: temp2_value["@id"] = org_value["@reverse"]
                else:
                    print("Error")
            else:
                if "@id" in temp2_value:
                    temp2_value["@id"] = org_value
                if "@reverse" in temp2_value:
                    temp2_value["@reverse"] = org_value

            temp1["_" + temp1_value["@id"].replace(":", "_")] = temp1_value
            temp2["_" + temp1_value["@id"].replace(":", "_")] = temp2_value

            # asume type mapping if key starts with capital letter
            if key[0].isupper():
                temp1[key] = None
                # temp3[org_key] = None

    print("temp1", temp1)
    print("temp2", temp2)
    print("temp3", temp3)
    graph = jsonld.compact(graph, {**transformation_context, **temp1})

    graph["@context"] = {**transformation_context, **temp2}
    graph = jsonld.flatten(graph)  # may introduce blank node @ids
    # graph = jsonld.expand(graph) # does not resolve @reverse relations

    graph = jsonld.compact(graph, {**transformation_context, **temp3})

    return graph


def json_to_json(
    document: dict, transformation_context: dict, document_context: dict = None
) -> dict:
    """Applies OO-LD alias notation to transform JSON documents

    Parameters
    ----------
    document
        input JSON document to transform
    transformation_context
        transformation context, which contains the mapping of aliases to URIs
    document_context
        context of the input document. Defaults to transformation_context

    Returns
    -------
        transformed JSON document
    """
    if document_context is None:
        document_context = transformation_context
    if type(document_context) is list:
        document = {"@graph": document}
    document["@context"] = document_context
    document = jsonld.expand(document)
    # anonymous_document = "@id" not in document
    # if "@graph" in document:
    #    # check none of the items in the graph has an @id
    #    anonymous_document = all("@id" not in item for item in document["@graph"])
    # check if json-string contains an @id
    anonymous_document = "@id" not in json.dumps(document)
    document = jsonld_to_jsonld(document, transformation_context)

    if anonymous_document:
        context = document["@context"]
        document = jsonld.expand(document)

        # if "@id" in document:
        #     del document["@id"]
        # if "@graph" in document:
        #     for item in document["@graph"]:
        #         if "@id" in item:
        #             del item["@id"]
        # recursively delete all @id keys in the document
        def remove_ids(d):
            if isinstance(d, dict):
                d.pop("@id", None)
                for key in list(d.keys()):
                    remove_ids(d[key])
            elif isinstance(d, list):
                for item in d:
                    remove_ids(item)

        remove_ids(document)
        document = jsonld.compact(document, context)
    del document["@context"]
    return document
