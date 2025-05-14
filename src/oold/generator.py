import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory

import datamodel_code_generator
from datamodel_code_generator import DataModelType, InputFileType, generate

from oold.utils.codegen import OOLDJsonSchemaParser


class Generator:
    def _generate(
        self,
        json_schemas,
        main_schema=None,
        output_model_type=DataModelType.PydanticV2BaseModel,
    ):
        # monkey patch class
        datamodel_code_generator.parser.jsonschema.JsonSchemaParser = (
            OOLDJsonSchemaParser
        )

        with TemporaryDirectory() as temporary_directory_name:
            temporary_directory = Path(temporary_directory_name)
            temporary_directory = Path(__file__).parent / "model" / "src"

            for schema in json_schemas:
                name = schema["id"]
                os.makedirs(
                    os.path.dirname(Path(temporary_directory / (name + ".json"))),
                    exist_ok=True,
                )
                with open(
                    Path(temporary_directory / (name + ".json")), "w", encoding="utf-8"
                ) as f:
                    schema_str = json.dumps(
                        schema, ensure_ascii=False, indent=4
                    ).replace("dollarref", "$ref")
                    # print(schema_str)
                    f.write(schema_str)

            input = Path(temporary_directory)
            output = Path(__file__).parent / "generated"
            if main_schema is not None:
                input = Path(temporary_directory / Path(main_schema))
                output = Path(__file__).parent / "model" / "model.py"

            if output_model_type == DataModelType.PydanticV2BaseModel:
                base_class = "oold.model.LinkedBaseModel"
            else:
                base_class = "oold.model.v1.LinkedBaseModel"
            generate(
                input_=input,
                # json_schema,
                input_file_type=InputFileType.JsonSchema,
                # input_filename="Foo.json",
                output=output,
                # set up the output model types
                output_model_type=output_model_type,
                # custom_template_dir=Path(model_dir_path),
                field_include_all_keys=True,
                base_class=base_class,
                # use_default = True,
                enum_field_as_literal="all",
                use_title_as_name=True,
                use_schema_description=True,
                use_field_description=True,
                encoding="utf-8",
                use_double_quotes=True,
                collapse_root_models=True,
                reuse_model=True,
                # create MyEnum(str, Enum) instead of MyEnum(Enum)
                use_subclass_enum=True,
                additional_imports=["pydantic.ConfigDict"]
                if output_model_type == DataModelType.PydanticV2BaseModel
                else [],
                apply_default_values_for_required_fields=True,
            )

            if main_schema is not None:
                content = ""
                with open(output, "r", encoding="utf-8") as f:
                    content = f.read()
                os.remove(output)

                content = re.sub(
                    r"(UUID = Field\(...)",
                    r"UUID = Field(default_factory=uuid4",
                    content,
                )  # enable default value for uuid

                if output_model_type == DataModelType.PydanticBaseModel:
                    # we are now using pydantic.v1
                    # pydantic imports lead to uninitialized fields
                    # (FieldInfo still present)
                    content = re.sub(
                        r"(from pydantic import)", "from pydantic.v1 import", content
                    )

                # write the content to the file
                with open(output, "w", encoding="utf-8") as f:
                    f.write(content)

    def preprocess(self, json_schemas):
        for schema in json_schemas:
            # schema = self.merge_property_schemas(schema)
            for property_key in schema.get("properties", {}):
                property = schema["properties"][property_key]
                if "range" in property:
                    if "type" in property:
                        del property["type"]
                    if "format" in property:
                        del property["format"]
                    # if range is a string we create a allOf with a ref to the range
                    if isinstance(property["range"], str):
                        property["allOf"] = [{"$ref": property["range"]}]
                    else:
                        property["$ref"] = property["range"]
                    if "required" in schema and property_key in schema["required"]:
                        # if no default value is set, remove the property from required
                        if "default" not in property:
                            schema["required"].remove(property_key)
                        if "x-oold-required-iri" not in property:
                            property["x-oold-required-iri"] = True
                if "items" in property:
                    if "range" in property["items"]:
                        if "type" in property["items"]:
                            del property["items"]["type"]
                        if "format" in property["items"]:
                            del property["items"]["format"]
                        if isinstance(property["items"]["range"], str):
                            property["items"]["allOf"] = [
                                {"$ref": property["items"]["range"]}
                            ]
                        else:
                            property["items"]["$ref"] = property["items"]["range"]
                        property["range"] = property["items"]["range"]
                        if "required" in schema and property_key in schema["required"]:
                            # if no default value is set,
                            # remove the property from required
                            if "default" not in property["items"]:
                                schema["required"].remove(property_key)
                            if "x-oold-required-iri" not in property:
                                property["x-oold-required-iri"] = True

                    if "properties" in property["items"]:
                        self.preprocess([property["items"]])

                if "properties" in property:
                    self.preprocess([property])

    def generate(
        self,
        json_schemas,
        main_schema=None,
        output_model_type=DataModelType.PydanticV2BaseModel,
    ):
        # pprint(json_schemas)
        self.preprocess(json_schemas)
        # pprint(json_schemas)
        self._generate(json_schemas, main_schema, output_model_type)
