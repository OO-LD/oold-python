import json
from pathlib import Path
from typing import Type, Union

import panel as pn
import param
from panel.custom import AnyWidgetComponent

from oold.model import LinkedBaseModel
from oold.model.v1 import LinkedBaseModel as LinkedBaseModel_v1

pn.extension()

bundled_assets_dir = Path(__file__).parent.parent.parent / "vue" / "dist" / "default"


class JsonEditor(AnyWidgetComponent):
    """A JSON-SCHEMA based form editor using
    https://github.com/json-editor/json-editor"""

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
    ready = param.Boolean(default=False, doc="Indicates if the JSONEditor is ready.")

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

    def set_schema(self, schema: dict, keep_value: bool = True):
        """Set the schema of the JSON editor."""
        # override options param to trigger change event
        new_options = {**self.options, "schema": schema}
        if keep_value:
            new_options["startval"] = self.get_value()
        else:
            new_options["startval"] = None
        self.options = new_options


class OoldEditor(JsonEditor):
    """JsonEditor generated from an oold model schema."""

    def __init__(
        self,
        oold_model: Union[Type[LinkedBaseModel], Type[LinkedBaseModel_v1]] = None,
        **params
    ):
        options = params.get("options", {})

        if oold_model is not None:
            options["schema"] = oold_model.export_schema()
        else:
            options["schema"] = {}

        params["options"] = options
        super().__init__(**params)
