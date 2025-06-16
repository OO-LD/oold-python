from static import _run


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


if __name__ == "__main__":
    test_oneof_subschema()
