import json
from pathlib import Path
from typing import Optional, Union

import panel as pn
import param
from panel.custom import AnyWidgetComponent

from oold.model import LinkedBaseModelMetaClass
from oold.model.v1 import LinkedBaseModelMetaClass as LinkedBaseModelMetaClass_v1

pn.extension()

bundled_assets_dir = Path(__file__).parent.parent.parent / "vue" / "dist" / "default"


# class JsonEditor(JSComponent):
class JsonEditor(AnyWidgetComponent):
    _esm = (bundled_assets_dir / "jsoneditor_vue.mjs").read_text()

    _stylesheets = [
        # includes bootstrap and spectre
        (bundled_assets_dir / "jsoneditor_vue.css").read_text(),
        # v5 does not work properly:
        # "https://cdn.jsdelivr.net/npm/bootstrap@4/dist/css/bootstrap.min.css",
        # does not work:
        # 'https://use.fontawesome.com/releases/v5.12.1/css/all.css',
        # "https://unpkg.com/spectre.css/dist/spectre-icons.min.css",
    ]
    _importmap = {
        "imports": {
            "vue": "https://esm.sh/vue@3",
            # works with `import {JSONEditor} from "@json-editor/json-editor"`:
            # "@json-editor/json-editor": "https://esm.sh/@json-editor/json-editor@latest",  # noqa
            # works with `import("@json-editor/json-editor")`:
            # "@json-editor/json-editor": (
            #   "https://cdn.jsdelivr.net/npm/@json-editor/json-editor",
            #   "@latest/dist/jsoneditor.min.js"
            # ),
            # works with `import("jsoneditor")`:
            "jsoneditor": "https://cdn.jsdelivr.net/npm/@json-editor/json-editor@latest/dist/jsoneditor.min.js",  # noqa
        }
    }
    # __javascript__= [
    #     "https://cdn.jsdelivr.net/npm/vue@2/dist/vue.js",
    #     "https://unpkg.com/bootstrap-vue@latest/dist/bootstrap-vue.min.js",
    #     "https://cdn.jsdelivr.net/npm/@json-editor/json-editor@latest/dist/jsoneditor.min.js"
    # ]
    value = param.Dict()
    options = param.Dict(
        default={
            # "theme": "bootstrap4",
            # "iconlib": 'fontawesome5',
            # "iconlib": "spectre",
            "schema": {
                "required": ["testxy"],
                "properties": {"testxy": {"type": "string"}},
            },
        }
    )

    encoder = param.ClassSelector(
        class_=json.JSONEncoder,
        is_instance=False,
        doc="""
    Custom JSONEncoder class used to serialize objects to JSON string.""",
    )

    def get_value(self):
        json_str = json.dumps(self.value, cls=self.encoder)
        return json.loads(json_str)

    def set_value(self, value: dict):
        """Set the value of the JSON editor."""
        self.value = value

    def set_schema(self, schema: dict):
        """Set the schema of the JSON editor."""
        self.options["schema"] = schema


class OswEditor(JsonEditor):
    # entity:  = Union[LinkedBaseModelMetaClass, LinkedBaseModelMetaClass_v1],
    def __init__(
        self,
        entity: Union[LinkedBaseModelMetaClass, LinkedBaseModelMetaClass_v1],
        **params
    ):
        options = {
            # "theme": "bootstrap4",
            # "iconlib": 'fontawesome5',
            # "iconlib": "spectre",
            "schema": {
                "required": ["testxy"],
                "properties": {"testxy": {"type": "string"}},
            },
        }

        if entity is not None:
            if isinstance(entity, LinkedBaseModelMetaClass_v1):
                schema = entity.schema()
            else:
                schema = entity.model_json_schema()
            options["schema"] = schema

        params["options"] = options
        super().__init__(**params)


if __name__ == "__main__":
    # jsoneditor = JsonEditor(height=500, max_width=800)
    from oold.model.v1 import LinkedBaseModel

    class Item(LinkedBaseModel):

        """A sample item model."""

        name: str
        description: Optional[str] = "This is a sample item description."

        class Config:
            schema_extra = {
                "required": ["name"],
                "defaultProperties": ["name", "description"],
            }

    jsoneditor = OswEditor(Item)
    pn.serve(
        pn.Column(
            jsoneditor, pn.pane.JSON(jsoneditor.param.value, theme="light")
        ).servable()
    )

    jsoneditor.get_value()
