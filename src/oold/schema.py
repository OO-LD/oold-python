import json

from oold.utils.oold import merge_deep


class OoldSchema:
    def __init__(self, args):
        defaultConfig = {
            "mode": "default",  # options: default, query
            "lang": "en",
            # see https://flatpickr.js.org/formatting/#time-formatting-tokens
            "format": {
                "date": "Y-m-d",
                "time": "H:i",
                "datetime-local": "Y-m-d H:i",
            },
            "use_cache": True,  # use local store schema cache
        }
        # Merge defaultConfig with args.config
        self.config = merge_deep(defaultConfig, args.get("config", {}))
        jsonschema = args.get("jsonschema", {})

        if isinstance(jsonschema, str):
            jsonschema = json.loads(jsonschema)
        jsonschema["id"] = jsonschema.get("id", "root")
        self._jsonschema = jsonschema
        self._context = {}
        self.subschemas_uuids = []
        self.data_source_maps = []

    # Generated from https://github.com/OpenSemanticLab/mediawiki-extensions-MwJson/blob/dfed7f817863a9dbd272baafaf5a338394679c4a/modules/ext.MwJson.util/MwJson_schema.js#L177 # noqa
    def _preprocess(self, params):
        schema = params.get("schema")
        level = params.get("level", 0)
        translateables = [
            "title",
            "description",
            "enum_titles",
            "default",
            "inputAttributes",
        ]
        visited_properties = params.get("visited_properties", [])

        if "allOf" in schema:
            # Apply allOf refs, while storing visited properties to detect overrides
            subschemas = (
                schema["allOf"]
                if isinstance(schema["allOf"], list)
                else [schema["allOf"]]
            )
            for subschema in subschemas:
                self._preprocess(
                    {
                        "schema": subschema,
                        "level": level + 1,
                        "visited_properties": visited_properties,
                    }
                )

        if "oneOf" in schema:
            # Apply oneOf refs, while discarding visited properties since the actual applied schema is unknown
            subschemas = (
                schema["oneOf"]
                if isinstance(schema["oneOf"], list)
                else [schema["oneOf"]]
            )
            for subschema in subschemas:
                self._preprocess({"schema": subschema, "level": level + 1})

        if "anyOf" in schema:
            # Apply anyOf refs, while discarding visited properties since the actual applied schema is unknown
            subschemas = (
                schema["anyOf"]
                if isinstance(schema["anyOf"], list)
                else [schema["anyOf"]]
            )
            for subschema in subschemas:
                self._preprocess({"schema": subschema, "level": level + 1})

        if "definitions" in schema:
            # Follow partial schemas in #/definitions
            for property in schema["definitions"]:
                self._preprocess(
                    {
                        "schema": schema["definitions"][property],
                        "level": level + 1,
                        "visited_properties": visited_properties,
                    }
                )

        if "$defs" in schema:
            # Follow partial schemas in #/$defs
            for property in schema["$defs"]:
                self._preprocess(
                    {
                        "schema": schema["$defs"][property],
                        "level": level + 1,
                        "visited_properties": visited_properties,
                    }
                )

        # Fix issue with $ref paths
        if "$ref" in schema and isinstance(schema["$ref"], str):
            schema["$ref"] = schema["$ref"].replace("%24defs", "$defs")

        # Include all required properties within defaultProperties
        if "required" in schema:
            if "defaultProperties" not in schema:
                schema["defaultProperties"] = []
            # Insert required before existing defaultProperties
            schema["defaultProperties"] = (
                schema["required"] + schema["defaultProperties"]
            )
            # Remove duplicates while preserving order
            seen = set()
            schema["defaultProperties"] = [
                x for x in schema["defaultProperties"] if not (x in seen or seen.add(x))
            ]

        # Translate attributes on schema level
        for attr in translateables:
            if attr + "*" in schema:
                if self.config.lang in schema[attr + "*"]:
                    schema[attr] = schema[attr + "*"][self.config.lang]
            if "options" in schema:
                if attr + "*" in schema["options"]:
                    if self.config.lang in schema["options"][attr + "*"]:
                        schema["options"][attr] = schema["options"][attr + "*"][
                            self.config.lang
                        ]

        # Handle string literal arrays
        if (
            schema.get("type") == "array"
            and schema.get("format") == "table"
            and schema.get("items", {}).get("type") == "string"
        ):
            schema["items"]["title"] = schema["items"].get("title", schema.get("title"))

        # Handle select input elements
        if (
            schema.get("type") == "array"
            and schema.get("uniqueItems") is True
            and "enum" in schema.get("items", {})
        ):
            schema["format"] = "selectize"

        # Handle time, date, and datetime-local format
        fmt = schema.get("format")
        if fmt in ["date", "time", "datetime", "datetime-local"]:
            # json-schema specifies datetime, json-editor uses datetime-local
            if fmt == "datetime":
                fmt = schema["format"] = "datetime-local"
            storeFormats = {"date": "Y-m-d", "time": "H:i", "datetime-local": "Z"}
            displayFormats = self.config.format
            schema.setdefault("options", {})
            schema["options"].setdefault("flatpickr", {})
            schema["options"]["flatpickr"]["dateFormat"] = schema["options"][
                "flatpickr"
            ].get("dateFormat", storeFormats.get(fmt))

            # Set altInput option if not explicitly disabled
            if schema["options"]["flatpickr"].get("altInput", True) is not False:
                schema["options"]["flatpickr"]["altInput"] = True
                schema["options"]["flatpickr"]["altFormat"] = schema["options"][
                    "flatpickr"
                ].get("altFormat", displayFormats.get(fmt))

        # Translate attributes on property level
        if "properties" in schema:
            for property in list(schema["properties"]):
                # Handle properties of type object and oneOf/anyOf on property level
                self._preprocess({"schema": schema["properties"][property]})

                # Handle array items
                if "items" in schema["properties"][property]:
                    self._preprocess(
                        {"schema": schema["properties"][property]["items"]}
                    )

                # Adjust propertyOrder based on nesting level
                prop_order = schema["properties"][property].get("propertyOrder")
                if prop_order is None and property not in visited_properties:
                    schema["properties"][property]["propertyOrder"] = 1000
                prop_order = schema["properties"][property]["propertyOrder"]
                if prop_order < 0:
                    # Absolute value - currently not ranked correctly
                    schema["properties"][property]["propertyOrder"] = prop_order
                elif prop_order <= 1000:
                    # Insert on top, rank higher levels before lower levels
                    schema["properties"][property]["propertyOrder"] = (
                        1000000 - level * 2000
                    ) + prop_order
                else:
                    # Insert on bottom, rank higher levels after lower levels
                    schema["properties"][property]["propertyOrder"] = (
                        1000000 + level * 2000
                    ) + prop_order

                # Filter properties according to mode
                if self.config.mode != "default":
                    options = schema["properties"][property].setdefault("options", {})
                    conditional_visible = options.get("conditional_visible", {})
                    modes = conditional_visible.get("modes", [])
                    if self.config.mode not in modes:
                        options["hidden"] = True
                    else:
                        options["hidden"] = False
                    if self.config.mode == "query" and options.get("hidden"):
                        # Remove hidden fields completely
                        del schema["properties"][property]
                        # Remove from required and defaultProperties
                        if "required" in schema:
                            schema["required"] = [
                                e for e in schema["required"] if e != property
                            ]
                            if not schema["required"]:
                                del schema["required"]
                        if "defaultProperties" in schema:
                            schema["defaultProperties"] = [
                                e for e in schema["defaultProperties"] if e != property
                            ]
                            if not schema["defaultProperties"]:
                                del schema["defaultProperties"]
                else:
                    # Remove query properties in default mode
                    options = schema["properties"][property].get("options", {})
                    conditional_visible = options.get("conditional_visible", {})
                    modes = conditional_visible.get("modes", [])
                    if self.config.mode not in modes:
                        del schema["properties"][property]
                        # Remove from required and defaultProperties
                        if "required" in schema:
                            schema["required"] = [
                                e for e in schema["required"] if e != property
                            ]
                        if "defaultProperties" in schema:
                            schema["defaultProperties"] = [
                                e for e in schema["defaultProperties"] if e != property
                            ]
                visited_properties.append(property)

        # Merge nested context over general context
        if "@context" in schema:
            self._context = merge_deep(schema["@context"], self._context)
        if "uuid" in schema:
            self.subschemas_uuids.append(schema["uuid"])
        if "data_source_maps" in schema:
            self.data_source_maps.extend(schema["data_source_maps"])
        return schema
