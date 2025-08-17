from typing import Optional, Type, Union

import panel as pn
from rdflib import Graph

from oold.model import LinkedBaseModel
from oold.model.v1 import LinkedBaseModel as LinkedBaseModel_v1
from oold.ui.panel import JsonEditor

pn.extension("codeeditor")


class OoldDemoEditor(pn.viewable.Viewer):
    def __init__(
        self,
        oold_model: Union[Type[LinkedBaseModel], Type[LinkedBaseModel_v1]] = None,
        options: Optional[dict] = None,
        **params
    ):
        options = params.get("options", {})
        json_editor_options = options.get("json_editor", {})
        if oold_model is not None:
            json_editor_options["schema"] = oold_model.export_schema()

        self._oold_model = oold_model

        super().__init__(**params)

        self.message = pn.pane.Markdown(
            """This is a schema generated editor that
            generates RDF directly from your input"""
        )
        self.jsoneditor = JsonEditor(
            # min_height=500,
            # max_height=500,
            sizing_mode="stretch_width",
            options=json_editor_options,
        )

        self.code_editor = pn.widgets.CodeEditor(
            value="", sizing_mode="stretch_width", language="turtle", height=300
        )

        self.save_btn_clicked = False
        self.save_btn = pn.widgets.Button(
            css_classes=["save_btn"], name="Save", button_type="primary"
        )

        self.jsoneditor.param.watch(self.on_value_change, "value")
        pn.bind(self.on_save, self.save_btn, watch=True)

        self._view = pn.Column(
            self.message,
            pn.Row(self.jsoneditor, scroll=True),
            # display jsoneditor value in a JSON pane for debugging
            # pn.pane.JSON(self.jsoneditor.param.value, theme="light"),
            pn.pane.Markdown(
                "### RDF Representation (Turtle format)", sizing_mode="stretch_width"
            ),
            self.code_editor,
            self.save_btn,
            scroll=True,
            width=800,
        )

    def on_value_change(self, event):
        """Handle changes in the value."""
        # Here you can handle the change event, e.g., save to a database or file
        print("Value changed:", self.jsoneditor.get_value())
        # You can also update the schema or perform other actions based on the new value
        # self.set_schema(self.options["schema"], keep_value=True)

        # construct oold model instance
        instance = None
        try:
            instance = self._oold_model(**self.jsoneditor.get_value())
            print("Valid instance created:", instance)
        except Exception as ex:
            print("Error creating instance:", ex)

        # Update the code editor with the RDF representation
        if instance is not None:
            g = Graph()
            g.parse(data=instance.to_jsonld(), format="json-ld")
            self.code_editor.value = g.serialize(format="turtle")

    def on_save(self, event):
        # Handle the save event here
        print("on_save")
        self.save_btn_clicked = True

    def __panel__(self):
        return self._view
