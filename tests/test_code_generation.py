from static import _run

from oold.model.static import enum_docstrings as parse_enum_docstrings


def test_oneof_subschema():
    # json schema with property that contains a oneOf with two subschemas

    schemas = [
        {
            "id": "example",
            "title": "Example",
            "type": "object",
            "properties": {
                "type": {"type": "string", "default": ["example"]},
                "prop1": {"type": "string", "custom_key": "custom_value"},
                "prop2": {
                    "custom_key": "custom_value",
                    "properties": {
                        "subprop0": {"type": "string", "custom_key": "custom_value_0"},
                    },
                    "oneOf": [
                        {
                            "title": "Subschema1",
                            "type": "object",
                            "properties": {
                                "subprop1": {
                                    "type": "string",
                                    "custom_key": "custom_value_1",
                                },
                            },
                        },
                        {
                            "title": "Subschema2",
                            "type": "object",
                            "properties": {
                                "subprop2": {
                                    "type": "string",
                                    "custom_key": "custom_value_2",
                                },
                            },
                        },
                    ],
                },
            },
        },
    ]

    def oneof_subschema(pydantic_version):
        # Test the generated model, see
        # https://github.com/koxudaxi/datamodel-code-generator/issues/2403

        if pydantic_version == "v1":
            import data.oneof_subschema.model_v1 as model

            assert (
                model.Subschema1.__fields__["subprop1"].field_info.extra["custom_key"]
                == "custom_value_1"
            )
        else:
            import data.oneof_subschema.model_v2 as model

            model.Subschema1.model_fields["subprop1"].json_schema_extra[
                "custom_key"
            ] == "custom_value_1"

    _run(
        schemas,
        main_schema="example.json",
        test=oneof_subschema,
        # pydantic_versions=["v1"],
    )


def test_enum_docstrings():
    schemas = [
        {
            "id": "example",
            "title": "Example",
            "type": "object",
            "properties": {
                "type": {"type": "string", "default": ["example"]},
                "hobby": {
                    "type": "string",
                    "enum": ["ex:sports", "ex:music", "ex:art"],
                    "description": "Defines various hobbies as an enum.",
                    "x-enum-varnames": ["SPORTS", "MUSIC", "ART"],
                    "options": {
                        "enum_titles": [
                            "Sports hobby, e.g. football, basketball, etc.",
                            "Music hobby, e.g. playing instruments, singing, etc.",
                            "Art hobby, e.g. painting, drawing, etc.",
                        ]
                    },
                },
            },
        },
    ]

    def enum_docstrings(pydantic_version):
        # Test the generated model, see
        # https://github.com/koxudaxi/datamodel-code-generator/issues/2403

        if pydantic_version == "v1":
            import data.enum_docstrings.model_v1 as model

            Hobby = parse_enum_docstrings(model.Hobby)
            assert (
                Hobby.SPORTS.__doc__.strip()
                == "Sports hobby, e.g. football, basketball, etc."
            )
            assert (
                Hobby.MUSIC.__doc__.strip()
                == "Music hobby, e.g. playing instruments, singing, etc."
            )
            assert (
                Hobby.ART.__doc__.strip() == "Art hobby, e.g. painting, drawing, etc."
            )
        else:
            import data.enum_docstrings.model_v2 as model

            Hobby = parse_enum_docstrings(model.Hobby)
            assert (
                Hobby.SPORTS.__doc__.strip()
                == "Sports hobby, e.g. football, basketball, etc."
            )
            assert (
                Hobby.MUSIC.__doc__.strip()
                == "Music hobby, e.g. playing instruments, singing, etc."
            )
            assert (
                Hobby.ART.__doc__.strip() == "Art hobby, e.g. painting, drawing, etc."
            )

    _run(
        schemas,
        main_schema="example.json",
        test=enum_docstrings,
        # pydantic_versions=["v1"],
    )


if __name__ == "__main__":
    test_oneof_subschema()
    test_enum_docstrings()
