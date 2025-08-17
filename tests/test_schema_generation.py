import json
from typing import Optional

import jsondiff

from oold.model.static import SchemaExportMode


def _run(pydantic_version="v1"):
    if pydantic_version == "v1":
        from pydantic.v1 import BaseModel, Field

        from oold.model.v1 import LinkedBaseModel

        class SubObject(BaseModel):
            prop1: int
            prop2: int

        class MyRootSchema(LinkedBaseModel):
            class Config:
                schema_extra = {
                    "@context": [
                        {"some_property": "https://example.org/some_property"},
                    ]
                }

        class MyCustomSchema(MyRootSchema):
            class Config:
                schema_extra = {
                    "@context": [
                        {"my_property": "https://example.org/my_property"},
                    ],
                }

            a_simple_property: int
            """
            A simple test
            """
            my_property: Optional[str] = Field(
                "default value",
                title="My property",
                title_={"de": "Mein Attribut"},
                description="A test property",
                description_={"de": "Dies ist ein Test-Attribut"},
            )

            a_object_property: SubObject

    else:
        from pydantic import BaseModel, Field

        from oold.model import LinkedBaseModel

        class SubObject(BaseModel):
            prop1: int
            prop2: int

        class MyRootSchema(LinkedBaseModel):
            model_config = {
                "json_schema_extra": {
                    "@context": [
                        {"some_property": "https://example.org/some_property"},
                    ]
                }
            }

        class MyCustomSchema(MyRootSchema):
            model_config = {
                "json_schema_extra": {
                    "@context": [
                        {"my_property": "https://example.org/my_property"},
                    ],
                }
            }

            a_simple_property: int
            """
            A simple test
            """
            my_property: Optional[str] = Field(
                "default value",
                title="My property",
                title_={"de": "Mein Attribut"},
                description="A test property",
                description_={"de": "Dies ist ein Test-Attribut"},
            )

            a_object_property: SubObject

    my_schema = MyCustomSchema.export_schema(mode=SchemaExportMode.PARTIAL)

    print(json.dumps(my_schema, indent=2))
    expected = {
        "@context": [
            "MyRootSchema",
            {"my_property": "https://example.org/my_property"},
        ],
        "$defs": {
            "SubObject": {
                "title": "SubObject",
                "type": "object",
                "properties": {
                    "prop1": {"title": "Prop1", "type": "integer"},
                    "prop2": {"title": "Prop2", "type": "integer"},
                },
                "required": ["prop1", "prop2"],
            }
        },
        "title": "MyCustomSchema",
        "type": "object",
        "properties": {
            "a_simple_property": {"title": "A Simple Property", "type": "integer"},
            "my_property": {
                "title": "My property",
                "description": "A test property",
                "default": "default value",
                "title*": {"de": "Mein Attribut"},
                "description*": {"de": "Dies ist ein Test-Attribut"},
                "type": "string",
            },
            "a_object_property": {"$ref": "#/$defs/SubObject"},
        },
        "required": ["a_simple_property", "a_object_property"],
    }
    diff = jsondiff.diff(my_schema, expected)
    assert diff == {}, f"Schema mismatch for {pydantic_version}:\n{diff}"


def test_schema_generation():
    _run(pydantic_version="v1")
    _run(pydantic_version="v2")


if __name__ == "__main__":
    # Run the test function
    test_schema_generation()
