from static import _run

from oold.static import enum_docstrings as parse_enum_docstrings


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


def test_subclass_inheritance():
    """
    Test that subclass inheritance of properties from parent classes works correctly.
    """

    schemas = [
        {
            "id": "Thing",
            "title": "Thing",
            "type": "object",
            "required": ["type", "name"],
            "properties": {
                "type": {
                    "type": "string",
                    "default": "playground:Thing",
                    "options": {"hidden": True},
                },
                "name": {
                    "type": "string",
                    "description": "The things name",
                    "minLength": 1,
                    "default": "A Thing",
                },
            },
        },
        {
            "id": "Person",
            "title": "Person",
            "type": "object",
            "allOf": [{"$ref": "Thing.json"}],
            "required": ["name"],
            "properties": {
                "type": {
                    "$comment": "Already defined in playground:Thing -> we override just the default",  # noqa: E501
                    "default": "playground:Person",
                },
                "name": {
                    "description": "First and Last name",
                    "minLength": 4,
                    "default": "John Doe",
                },
                "age": {"type": "integer"},
            },
        },
    ]

    def subclass_inheritance(pydantic_version):
        # 'Person' should be a subclass of 'Thing' and inherit its properties
        # the default value of 'name' in 'Thing' should be 'A Thing'
        # the default value of 'name' in 'Person' should be 'John Doe'
        # the type of 'name' in 'Person' should be string

        if pydantic_version == "v1":
            import data.subclass_inheritance.model_v1 as model

            assert issubclass(model.Person, model.Thing)
            assert model.Thing.__fields__["name"].default == "A Thing"
            assert model.Person.__fields__["name"].default == "John Doe"
            # fails with datamodel-code-generator 0.28.2, fixed in 0.43.1
            assert str(model.Person.__fields__["type"].annotation) == "str | None"

        else:
            import data.subclass_inheritance.model_v2 as model

            assert issubclass(model.Person, model.Thing)
            assert model.Thing.model_fields["name"].default == "A Thing"
            assert model.Person.model_fields["name"].default == "John Doe"
            assert str(model.Person.model_fields["type"].annotation) == "str | None"

    _run(
        schemas,
        main_schema="Person.json",
        test=subclass_inheritance,
    )


def test_class_hierarchy():
    schemas = [
        {
            "id": "NestedSubSchema",
            "title": "NestedSubSchema",
            "description": "An example subschema",
            "type": "object",
            "properties": {
                "subschema": {
                    "title": "SimpleSubSchema",
                    "type": "object",
                    "properties": {"some_property": {"type": "string"}},
                }
            },
        },
        {
            "id": "OtherEntity",
            "type": "object",
            "properties": {
                "nested": {
                    "type": "array",
                    "items": {
                        "title": "NestedSubSchema",
                        "x-custom-annotation": "custom value",
                        # "allOf": [{
                        "$ref": "NestedSubSchema.json"
                        # }]
                    },
                }
            },
        },
        {
            "id": "Entity",
            "title": "Entity",
            "type": "object",
            "properties": {
                "nested": {
                    "title": "EntityNestedSubSchema",
                    "description": "An example using a subschema",
                    "x-custom-annotation": "custom value",
                    # "allOf": [{
                    "$ref": "NestedSubSchema.json"
                    # }]
                }
            },
        },
    ]

    def class_hierarchy(pydantic_version):
        # test if the generated modul contains exactly three classes:
        # Entity, NestedSubSchema, SimpleSubSchema

        if pydantic_version == "v1":
            import data.class_hierarchy.model_v1 as model

        else:
            import data.class_hierarchy.model_v2 as model

        assert hasattr(model, "Entity")
        assert hasattr(model, "NestedSubSchema")
        assert hasattr(model, "SimpleSubSchema")
        # ignore imported classes and only count classes defined in the module
        classes = [
            cls_name
            for cls_name in dir(model)
            if isinstance(getattr(model, cls_name), type)
            and getattr(model, cls_name).__module__ == model.__name__
        ]
        assert set(classes) == {"Entity", "NestedSubSchema", "SimpleSubSchema"}

        # test if type annotation of Entity.nested is Optional[NestedSubSchema]
        # and NestedSubSchema.subschema is Optional[SimpleSubSchema]
        if pydantic_version == "v1":
            import data.class_hierarchy.model_v1 as model

            assert (
                str(model.Entity.__fields__["nested"].annotation)
                == "data.class_hierarchy.model_v1.NestedSubSchema | None"
            )
            assert (
                str(model.NestedSubSchema.__fields__["subschema"].annotation)
                == "data.class_hierarchy.model_v1.SimpleSubSchema | None"
            )
        else:
            import data.class_hierarchy.model_v2 as model

            assert (
                str(model.Entity.model_fields["nested"].annotation)
                == "data.class_hierarchy.model_v2.NestedSubSchema | None"
            )
            assert (
                str(model.NestedSubSchema.model_fields["subschema"].annotation)
                == "data.class_hierarchy.model_v2.SimpleSubSchema | None"
            )

    _run(
        schemas,
        main_schema="Entity.json",
        test=class_hierarchy,
    )


if __name__ == "__main__":
    test_oneof_subschema()
    test_enum_docstrings()
    test_subclass_inheritance()
    test_class_hierarchy()
