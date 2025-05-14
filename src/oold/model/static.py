from typing import Callable, Dict

import pyld
from pydantic import BaseModel
from pydantic.v1 import BaseModel as BaseModel_v1
from pyld import jsonld


class GenericLinkedBaseModel:
    def _object_to_iri(self, d, exclude_none=False):
        for name in list(d.keys()):  # force copy of keys for inline-delete
            if name in self.__iris__:
                d[name] = self.__iris__[name]
            if exclude_none and d[name] is None:
                del d[name]
        return d

    @staticmethod
    def remove_none(d: Dict) -> Dict:
        """Remove None values from a dictionary recursively."""
        if isinstance(d, dict):
            return {
                k: GenericLinkedBaseModel.remove_none(v)
                for k, v in d.items()
                if v is not None
            }
        elif isinstance(d, list):
            return [GenericLinkedBaseModel.remove_none(i) for i in d]
        else:
            return d


def get_jsonld_context_loader(model_cls, model_type) -> Callable:
    """to overwrite the default jsonld document loader to load
    relative context from the osl"""

    classes = [model_cls]
    i = 0
    while 1:
        try:
            cls = classes[i]
            if cls == model_type:
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
    if "id" not in data and "@id" not in data:
        data["id"] = model_instance.get_iri()
    jsonld_dict = {"@context": context, **data}
    jsonld.set_document_loader(
        get_jsonld_context_loader(model_instance.__class__, model_type)
    )
    jsonld_dict = jsonld.expand(jsonld_dict)
    if isinstance(jsonld_dict, list):
        jsonld_dict = jsonld_dict[0]
    return jsonld_dict


def import_jsonld(model_type, jsonld_dict: Dict, _types: Dict[str, type]):
    """Return the object instance from the JSON-LD representation."""
    # ToDo: apply jsonld frame with @id restriction
    # get the @type from the jsonld_dict
    type_iri = jsonld_dict.get("@type", None)
    # if type_iri is None, return None
    if type_iri is None:
        return None
    # if type_iri is a list, get the first element
    if isinstance(type_iri, list):
        type_iri = type_iri[0]
    # get the class from the _types dict
    # Todo: IRI normalization
    type_iri = type_iri.split("/")[-1]
    model_cls = _types.get(type_iri, None)
    # if model_type is None, return None
    if model_cls is None:
        return None
    if model_type == BaseModel:
        # get the context from self.ConfigDict.json_schema_extra["@context"]
        context = model_cls.model_config.get("json_schema_extra", {}).get(
            "@context", {}
        )
    if model_type == BaseModel_v1:
        context = model_cls.__config__.schema_extra.get("@context", {})
    jsonld.set_document_loader(get_jsonld_context_loader(model_cls, model_type))
    jsonld_dict = jsonld.compact(jsonld_dict, context)
    if "@context" in jsonld_dict:
        del jsonld_dict["@context"]
    return model_cls(**jsonld_dict)
