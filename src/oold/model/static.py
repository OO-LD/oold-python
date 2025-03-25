from typing import Callable, Dict

import pyld
from pydantic import BaseModel
from pydantic.v1 import BaseModel as BaseModel_v1
from pyld import jsonld


class GenericLinkedBaseModel:
    pass


def get_jsonld_context_loader(model_instance, model_type) -> Callable:
    """to overwrite the default jsonld document loader to load
    relative context from the osl"""

    classes = [model_instance.__class__]
    i = 0
    while 1:
        try:
            cls = classes[i]
            if cls == BaseModel:
                break
        except IndexError:
            break
        i += 1
        classes[i:i] = [base for base in cls.__bases__ if base not in classes]

    schemas = {}
    for base_class in classes:
        schema = {}
        if model_type == BaseModel:
            if hasattr(base_class, "model_config"):
                schema = base_class.model_config.get("json_schema_extra", {})
        if model_type == BaseModel_v1:
            if hasattr(base_class, "__config__"):
                schema = base_class.__config__.schema_extra
        id = schema.get("iri", None)
        schemas[id] = schema

    # print(schemas)

    def loader(url, options=None):
        if options is None:
            options = {}
        # print("Requesting", url)
        if url in schemas:
            schema = schemas[url]

            doc = {
                "contentType": "application/json",
                "contextUrl": None,
                "documentUrl": url,
                "document": schema,
            }
            # print("Loaded", doc)
            return doc

        else:
            requests_loader = pyld.documentloader.requests.requests_document_loader()
            return requests_loader(url, options)

    return loader


def export_jsonld(model_instance, model_type) -> Dict:
    """Return the RDF representation of the object as JSON-LD."""
    if model_type == BaseModel:
        # get the context from self.ConfigDict.json_schema_extra["@context"]
        context = model_instance.model_config.get("json_schema_extra", {}).get(
            "@context", {}
        )
    if model_type == BaseModel_v1:
        context = model_instance.__class__.__config__.schema_extra.get("@context", {})
    data = model_instance.dict()
    if "id" not in data and not "@id" not in data:
        data["id"] = model_instance.get_iri()
    jsonld_dict = {"@context": context, **data}
    jsonld.set_document_loader(get_jsonld_context_loader(model_instance, model_type))
    jsonld_dict = jsonld.expand(jsonld_dict)
    if isinstance(jsonld_dict, list):
        jsonld_dict = jsonld_dict[0]
    return jsonld_dict
