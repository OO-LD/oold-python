import ast
import inspect
import json
from enum import Enum
from functools import partial
from operator import is_
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, Union

import jsondiff
import pydantic_core.core_schema as core_schema
import pyld
import yaml
from pydantic import BaseModel, create_model
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode, JsonSchemaValue
from pydantic.v1 import BaseModel as BaseModel_v1
from pydantic.v1 import create_model as create_model_v1
from pydantic_core import CoreSchema, to_jsonable_python
from pyld import jsonld
from typing_extensions import Literal

from oold.utils.environment import get_object_source

E = TypeVar("E", bound=Enum)


# from https://stackoverflow.com/a/79229811
# see also https://stackoverflow.com/a/78943193
def enum_docstrings(enum: type[E]) -> type[E]:
    '''Attach docstrings to enum members

    Docstrings are string literals that appear directly below the enum member
    assignment expression:

    ```
    @enum_docstrings
    class SomeEnum(Enum):
        """Docstring for the SomeEnum enum"""

        foo_member = "foo_value"
        """Docstring for the foo_member enum member"""

    SomeEnum.foo_member.__doc__  # 'Docstring for the foo_member enum member'
    ```

    '''
    source_code = get_object_source(enum)
    if source_code is None:
        return enum

    mod = ast.parse(source_code)
    if mod.body and isinstance(class_def := mod.body[0], ast.ClassDef):
        # An enum member docstring is unassigned if it is the exact same object
        # as enum.__doc__.
        unassigned = partial(is_, enum.__doc__)
        names = enum.__members__.keys()
        member: E | None = None
        for node in class_def.body:
            # case ast.Assign(targets=[ast.Name(id=name)]) if name in names:
            if isinstance(node, ast.Assign):
                if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                    name = node.targets[0].id
                    if name in names:
                        # Enum member assignment, look for a docstring next
                        member = enum[name]
                        continue

            # case ast.Expr(value=ast.Constant(value=str(docstring)))
            # if member and unassigned(member.__doc__):
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and member
                and unassigned(member.__doc__)
            ):
                # docstring immediately following a member assignment
                docstring = node.value.value
                member.__doc__ = docstring
            else:
                pass

            member = None

    return enum


class OOLDJsonSchemaGenerator(GenerateJsonSchema):
    def generate(
        self, schema: CoreSchema, mode: JsonSchemaMode = "validation"
    ) -> JsonSchemaValue:
        return super().generate(schema, mode)

    def nullable_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Override to handle nullable schemas - do not add 'null' type
        since optional fields are already handled by 'required'."""
        inner_json_schema = self.generate_inner(schema["schema"])
        return inner_json_schema

    def enum_schema(self, schema: core_schema.EnumSchema) -> JsonSchemaValue:
        """Generates a JSON schema that matches an Enum value.

        Args:
            schema: The core schema.

        Returns:
            The generated JSON schema.
        """
        enum_type = enum_docstrings(schema["cls"])
        description = (
            None if not enum_type.__doc__ else inspect.cleandoc(enum_type.__doc__)
        )
        if (
            description == "An enumeration."
        ):  # This is the default value provided by enum.EnumMeta.__new__; don't use it
            description = None
        result: dict[str, Any] = {
            "title": enum_type.__name__,
            "description": description,
        }
        result = {k: v for k, v in result.items() if v is not None}

        expected = [to_jsonable_python(v.value) for v in schema["members"]]

        result["enum"] = expected

        # interate over all enum values and collect their docstrings
        enum_descriptions = []
        for v in enum_type:
            if v.value in expected and v.__doc__:
                enum_descriptions.append(f"{inspect.cleandoc(v.__doc__)}")
            else:
                enum_descriptions.append(f"{v.value}")
        if "options" not in result:
            result["options"] = {}
        result["options"]["enum_titles"] = enum_descriptions

        result["x-enum-varnames"] = [v.name for v in enum_type if v.value in expected]
        result["x-enum-descriptions"] = enum_descriptions

        types = {type(e) for e in expected}
        if isinstance(enum_type, str) or types == {str}:
            result["type"] = "string"
        elif isinstance(enum_type, int) or types == {int}:
            result["type"] = "integer"
        elif isinstance(enum_type, float) or types == {float}:
            result["type"] = "number"
        elif types == {bool}:
            result["type"] = "boolean"
        elif types == {list}:
            result["type"] = "array"

        return result


class SchemaExportMode(str, Enum):
    """Enum for schema export modes."""

    FULL = "full"
    """Export the full schema including all base classes.
    Equivalent to cutoff at the BaseModel class"""
    PARTIAL = "partial"
    """Export the schema of a model up to the specified cutoff
    base class, default the direct parent class"""


class PartialSchemaExportMode(str, Enum):
    """Enum for partial schema export modes."""

    BASE_CLASS_CUTOFF = "base_class_cutoff"
    """Export the schema of a model up to the specified base class
    by cutoff the class hierarchy"""
    BASE_CLASS_DIFF = "base_class_diff"
    """Export the schema of a model up to the specified base class
    by calculating the diff to the base class schema."""


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

    @classmethod
    def export_schema(
        cls,
        mode: Optional[SchemaExportMode] = SchemaExportMode.FULL,
        cutoff_base_cls: Optional[
            Union[Union[BaseModel, BaseModel_v1], Tuple[Union[BaseModel, BaseModel_v1]]]
        ] = None,
        partial_mode: Optional[
            PartialSchemaExportMode
        ] = PartialSchemaExportMode.BASE_CLASS_CUTOFF,
        serialize: Optional[Literal["json", "yaml"]] = None,
    ) -> Dict:
        """Export the schema of the model as a dictionary."""
        schema = export_schema(cls, mode, cutoff_base_cls, partial_mode)
        if serialize == "json":
            return json.dumps(schema, indent=2)
        elif serialize == "yaml":
            _ignore_aliases = yaml.Dumper.ignore_aliases
            yaml.Dumper.ignore_aliases = lambda *args: True
            yaml_doc = yaml.dump(schema, indent=2)
            yaml.Dumper.ignore_aliases = _ignore_aliases
            return yaml_doc
        return schema


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
        iri = schema.get("iri", None)
        title = schema.get("title", None)
        if iri is None and title is None:
            continue
        if iri is None:
            schema.get("title")
            if title in ["Entity", "Category", "Property"]:
                iri = "Category:" + schema.get("title")
            else:
                iri = "Category:" + "OSW" + schema.get("uuid").replace("-", "")
        # iri = base_class.get_iri() # does not work on class level
        schemas[iri] = schema

    # print(schemas)

    def loader(url, options=None):
        if options is None:
            options = {}
        # print("Requesting", url)
        if "/wiki/" in url:
            url = url.split("/")[-1].split("?")[0]
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

    # serialize the model to a dictionary
    # to_string().to_json() roundtrips is needed to serialize enums correctly
    if model_type == BaseModel:
        # get the context from self.ConfigDict.json_schema_extra["@context"]
        context = model_instance.model_config.get("json_schema_extra", {}).get(
            "@context", {}
        )
        data = json.loads(model_instance.model_dump_json(exclude_none=True))
    if model_type == BaseModel_v1:
        context = model_instance.__class__.__config__.schema_extra.get("@context", {})
        data = json.loads(model_instance.json(exclude_none=True))

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


def _get_schema(model_cls):
    """Return the schema of the model as a dictionary."""
    if issubclass(model_cls, BaseModel):
        return model_cls.model_json_schema(
            ref_template="#/$defs/{model}",
            schema_generator=OOLDJsonSchemaGenerator,
        )
    elif issubclass(model_cls, BaseModel_v1):
        return model_cls.schema(ref_template="#/$defs/{model}")


def _inverse_preprocess(schema: Dict):
    """Inverse preprocess the JSON schemas to remove
    the $refs generated from x-oold-range annotations."""

    def handle_property(property):
        if "range" in property:
            # restore a string type, remove allOf and $ref
            # if they (or one element) match the range value
            if isinstance(property["range"], str):
                if "allOf" in property:
                    # remove the array element that matches the range
                    # or a self-referencing $ref
                    property["allOf"] = [
                        item
                        for item in property["allOf"]
                        if item["$ref"] in ["#", property["range"]]
                    ]
                if "$ref" in property:
                    if property["$ref"] in ["#", property["range"]]:
                        del property["$ref"]
            else:
                if "allOf" in property:
                    # remove the array element that matches the range
                    property["allOf"] = [
                        item for item in property["allOf"] if item == property["range"]
                    ]
            if "allOf" in property and len(property["allOf"]) == 0:
                del property["allOf"]
            if "type" not in property:
                property["type"] = "string"
        if "properties" in property:
            _inverse_preprocess(property)

    for property_key in schema.get("properties", {}):
        property = schema["properties"][property_key]
        if "x-oold-required-iri" in property:
            # remove the x-oold-required-iri property
            # add property to required
            del property["x-oold-required-iri"]
            if "required" not in schema:
                schema["required"] = []
            if property_key not in schema["required"]:
                schema["required"].append(property_key)

        if "items" in property:
            if "range" in property["items"]:
                property["items"]["range"] = property["range"]
                del property["range"]
            handle_property(property["items"])

        else:
            handle_property(property)
    return schema


def _export_schema_from_dynamic_model(
    model_cls: Union[BaseModel, BaseModel_v1]
) -> Dict:
    """Export the OO-LD schema of a single pydantic model.
    Class hierarchy is not considered, only the model itself
    by generating a model copy without base classes.
    """

    if issubclass(model_cls, BaseModel):
        field_dict = {}
        for field_name, field in model_cls.model_fields.items():
            field_dict[field_name] = (field.annotation, field)

        # create model dynamically
        model_cls_copy = create_model(
            model_cls.__name__,
            __config__=model_cls.model_config,
            __doc__=model_cls.__doc__,
            __module__=model_cls.__module__,
            **field_dict,
            # __base__=BaseModel,
        )

    elif issubclass(model_cls, BaseModel_v1):
        model_cls: BaseModel_v1 = model_cls  # type: ignore
        field_dict = {}
        for field_name, model_field in model_cls.__fields__.items():
            field_dict[field_name] = (model_field.annotation, model_field.field_info)

        # create model dynamically
        model_cls_copy = create_model_v1(
            model_cls.__name__,
            __config__=model_cls.__config__,
            __doc__=model_cls.__doc__,
            __module__=model_cls.__module__,
            **field_dict,
            # __base__=BaseModel_v1,
        )

    my_schema_full = _get_schema(model_cls_copy)

    return my_schema_full


def export_schema(
    model_cls: Union[BaseModel, BaseModel_v1],
    mode: Optional[SchemaExportMode] = SchemaExportMode.FULL,
    cutoff_base_cls: Optional[
        Union[Union[BaseModel, BaseModel_v1], Tuple[Union[BaseModel, BaseModel_v1]]]
    ] = None,
    partial_mode: Optional[
        PartialSchemaExportMode
    ] = PartialSchemaExportMode.BASE_CLASS_CUTOFF,
) -> Dict:
    """Export the OO-LD schema of the model as a JSON-SCHEMA with JSON-LD context"""

    if mode == SchemaExportMode.FULL:
        # export the full schema including all base classes
        result_schema = _get_schema(model_cls)
        if result_schema is None:
            raise ValueError(f"Model {model_cls.__name__} has no schema.")

    elif mode == SchemaExportMode.PARTIAL:
        # export the schema of a model up to the specified cutoff base class

        baseclass_schema = {}
        imports = []

        if cutoff_base_cls is None:
            cutoff_base_cls = model_cls.__bases__
        if not isinstance(cutoff_base_cls, tuple):
            cutoff_base_cls = (cutoff_base_cls,)

        # if partial_mode == PartialSchemaExportMode.BASE_CLASS_CUTOFF:

        for baseclass in cutoff_base_cls:
            if baseclass in [BaseModel, BaseModel_v1]:
                continue
            schema = _get_schema(baseclass)
            if schema is not None:
                # ToDO: Use deepmerge
                baseclass_schema = {**baseclass_schema, **schema}

            # ToDo: determine import references
            # baseclass_oswid = ""
            # if baseclass.__name__ in toplevel_classes:
            #     baseclass_oswid = toplevel_classes[baseclass.__name__]
            # else:
            #     baseclass_oswid = get_osw_id(
            #         baseclass.__config__.schema_extra["uuid"]
            #     )

            # imports.append(f"/wiki/Category:{baseclass_oswid}?action=raw&slot=jsonschema")
            # try the follwing schema extra attributes: $id, iri, class name
            import_ref = None
            if issubclass(model_cls, BaseModel):
                import_ref = baseclass.model_config.get("json_schema_extra", {}).get(
                    "$id", None
                )
                if import_ref is None:
                    import_ref = baseclass.model_config.get(
                        "json_schema_extra", {}
                    ).get("iri", None)
                if import_ref is None:
                    import_ref = baseclass.__name__

            if issubclass(model_cls, BaseModel_v1):
                import_ref = baseclass.__config__.schema_extra.get("$id", None)
                if import_ref is None:
                    import_ref = baseclass.__config__.schema_extra.get("iri", None)
                if import_ref is None:
                    import_ref = baseclass.__name__

            if import_ref is not None:
                imports.append(import_ref)

        if partial_mode == PartialSchemaExportMode.BASE_CLASS_DIFF:
            # option 1: calculate a schema diff
            # implementation not yet complete

            for baseclass in cutoff_base_cls:
                if baseclass in [BaseModel, BaseModel_v1]:
                    continue
                schema = _get_schema(baseclass)
                if schema is not None:
                    # ToDO: Use deepmerge
                    baseclass_schema = {**baseclass_schema, **schema}

            model_schema_full = _get_schema(model_cls)
            model_schema_diff = jsondiff.diff(
                baseclass_schema, model_schema_full, marshal=True
            )

            # implementation note: jsonpath does not work
            # since we cannot reconstruct the diff document
            # import jsonpatch
            # patch = jsonpatch.make_patch(baseclass_schema, model_schema_full)
            # print("Patch: ", json.dumps(patch.patch, indent=2))
            # this fails due to missing root paths
            # see https://github.com/stefankoegl/python-json-patch/issues/153
            # print("Diff: ", json.dumps(patch.apply({}), indent=2))

            required = []
            if "required" in model_schema_diff:
                if "$insert" in model_schema_diff["required"]:
                    for r in model_schema_diff["required"]["$insert"]:
                        required.append(r[1])
                    del model_schema_diff["required"]
            model_schema_diff["required"] = required
            if "$delete" in model_schema_diff:
                del model_schema_diff["$delete"]
            # todo: handle all "$insert", "$delete" and "$replace" keys

        elif partial_mode == PartialSchemaExportMode.BASE_CLASS_CUTOFF:
            # option 2: export the schema of a model up to the specified
            # base class by cutoff the class hierarchy
            model_schema_diff = _export_schema_from_dynamic_model(model_cls)

        context = None
        if "@context" in model_schema_diff:
            context = model_schema_diff.pop("@context")

            if not isinstance(context, list):
                context = [context]
            missing_imports = []
            for imp in imports:
                if imp not in context:
                    missing_imports.append(imp)
            context = [*missing_imports, *context]

        defs = None
        if "definitions" in model_schema_diff:
            defs = model_schema_diff.pop("definitions")
        if "$defs" in model_schema_diff:
            if defs is None:
                defs = {}
            defs = {**defs, **model_schema_diff.pop("$defs")}
        result_schema = {
            "@context": context,
            "$defs": defs,
            **json.loads(
                json.dumps(model_schema_diff)
                .replace("title_", "title*")
                .replace("description_", "description*")
                .replace("$$ref", "$ref")
            ),
        }

    # ToDo: move this to general json utils

    # if schema has a $ref on the root level, resolve it by following the reference
    # e.g. {"$defs": {"Entity": {"title": "Entity"}}, "$ref": "#/$defs/Entity"}
    # => {"title": "Entity"}
    if "$ref" in result_schema:
        ref = result_schema["$ref"]
        if ref.startswith("#/"):
            # follow the ref path elements
            ref_path = ref.split("/")[1:]  # remove the leading "#/"
            ref_target = result_schema
            for path_element in ref_path:
                if path_element in ref_target:
                    ref_target = ref_target[path_element]
                else:
                    raise ValueError(f"Reference {ref} not found in schema.")
            result_schema = {**ref_target, **result_schema}

            # rewrite other $ref to the current schema
            # => e.g. replace all {"$ref": "#/$defs/Entity"} with {"$ref": "#"}
            # iterate over all result_schema['properties']
            # and schema['properties']['items'] and remove the $ref
            refs = []
            for property_key in result_schema.get("properties", {}):
                property = result_schema["properties"][property_key]
                if "$ref" in property:
                    refs.append(property["$ref"])
                    if property["$ref"] == ref:
                        property["$ref"] = "#"
                if "items" in property:
                    if "$ref" in property["items"]:
                        refs.append(property["items"]["$ref"])
                        if property["items"]["$ref"] == ref:
                            property["items"]["$ref"] = "#"
            # if non of the refs is a subpath of the ref, remove $defs element
            # in case it is at root level of $defs
            if not any(_ref.startswith(ref + "/") for _ref in refs):
                if ref.split("/")[:-1] == ["#", "$defs"]:
                    del result_schema["$defs"][ref.split("/")[-1]]

            del result_schema["$ref"]
    result_schema = _inverse_preprocess(result_schema)
    return result_schema
