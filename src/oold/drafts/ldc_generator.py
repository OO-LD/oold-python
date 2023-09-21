import json
import os
import re
from pathlib import Path
from pprint import pprint
from tempfile import TemporaryDirectory
from typing import List, Optional

from datamodel_code_generator import DataModelType, InputFileType, generate
from datamodel_code_generator.parser.jsonschema import (
    JsonSchemaObject,
    JsonSchemaParser,
)


def generate1(json_schemas):
    code = ""
    first = True
    for schema in json_schemas:
        parser = JsonSchemaParser(
            json.dumps(schema),
            # custom_template_dir=Path(model_dir_path),
            field_include_all_keys=True,
            base_class="osw.model.static.OswBaseModel",
            # use_default = True,
            enum_field_as_literal="all",
            use_title_as_name=True,
            use_schema_description=True,
            use_field_description=True,
            encoding="utf-8",
            use_double_quotes=True,
            collapse_root_models=True,
            reuse_model=True,
        )
        content = parser.parse()

        if first:
            header = (
                "from uuid import uuid4\n"
                "from typing import Type, TypeVar\n"
                "from osw.model.static import OswBaseModel, Ontology\n"
                "\n"
            )

            content = re.sub(
                r"(class\s*\S*\s*\(\s*OswBaseModel\s*\)\s*:.*\n)",
                header + r"\n\n\n\1",
                content,
                1,
            )  # add header before first class declaration

            content = re.sub(
                r"(UUID = Field\(...)",
                r"UUID = Field(default_factory=uuid4",
                content,
            )  # enable default value for uuid

        else:
            org_content = code

            pattern = re.compile(
                r"class\s*([\S]*)\s*\(\s*\S*\s*\)\s*:.*\n"
            )  # match class definition [\s\S]*(?:[^\S\n]*\n){2,}
            for cls in re.findall(pattern, org_content):
                print(cls)
                content = re.sub(
                    r"(class\s*"
                    + cls
                    + r"\s*\(\s*\S*\s*\)\s*:.*\n[\s\S]*?(?:[^\S\n]*\n){3,})",
                    "",
                    content,
                    count=1,
                )  # replace duplicated classes

            content = re.sub(
                r"(from __future__ import annotations)", "", content, 1
            )  # remove import statement

        code += content + "\r\n"
        # pprint(parser.raw_obj)
        # print(result)
        first = False

    with open("model.py", "w") as f:
        f.write(code)


def generate2(json_schemas):
    with TemporaryDirectory() as temporary_directory_name:
        temporary_directory = Path(temporary_directory_name)
        temporary_directory = Path("./model")
        output = Path(temporary_directory / "model.py")
        for schema in json_schemas:
            name = schema["id"]
            with open(
                Path(temporary_directory / (name + ".json")), "w", encoding="utf-8"
            ) as f:
                schema_str = json.dumps(schema, ensure_ascii=False, indent=4).replace(
                    "dollarref", "$ref"
                )
                # print(schema_str)
                f.write(schema_str)
        generate(
            input_=Path(temporary_directory / "Foo.json"),
            # json_schema,
            input_file_type=InputFileType.JsonSchema,
            input_filename="Foo.json",
            output=output,
            # set up the output model types
            output_model_type=DataModelType.PydanticV2BaseModel,
            # custom_template_dir=Path(model_dir_path),
            field_include_all_keys=True,
            base_class="static.LinkedBaseModel",
            # use_default = True,
            enum_field_as_literal="all",
            use_title_as_name=True,
            use_schema_description=True,
            use_field_description=True,
            encoding="utf-8",
            use_double_quotes=True,
            collapse_root_models=True,
            reuse_model=True,
        )


def get_schemas():
    json_schemas = [
        {
            "id": "Bar",
            "title": "Bar",
            "type": "object",
            "properties": {
                "type": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Bar"],
                },
                "prop1": {"type": "string"},
            },
        },
        {
            "id": "Foo",
            "title": "Foo",
            "type": "object",
            "properties": {
                "type": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["Foo"],
                },
                "literal": {"type": "string"},
                "b": {"type": "string", "range": "Bar"},
                "b2": {"$ref": "Bar.json", "range": "Bar"},
            },
        },
    ]
    return json_schemas


def preprocess(json_schemas):
    aggr_schema = {"$defs": {}}
    for schema in json_schemas:
        aggr_schema["$defs"][schema["id"]] = schema
    # pprint(aggr_schema)
    return aggr_schema


js = get_schemas()
pprint(js)
# js = preprocess(js)
generate2(js)
