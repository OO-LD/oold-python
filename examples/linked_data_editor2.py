from typing import Optional

import panel as pn

from oold.ui.panel import OoldEditor


def test1():
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

    jsoneditor = OoldEditor(Item)
    index = 1

    def on_save(event):
        # Here you can handle the save event, e.g., save to a database or file
        global index
        print("Save button clicked")
        print("Current value:", jsoneditor.get_value())
        # jsoneditor.value = {"name": "New Item", "description": "This is a new item." + str(index)}
        jsoneditor.options = {
            **jsoneditor.options,
            "schema": {**jsoneditor.options["schema"], "title": "Item " + str(index)},
            "startval": jsoneditor.get_value(),  # keep the current value
        }
        index = index + 1

    save_btn = pn.widgets.Button(name="Save", button_type="primary")
    pn.bind(on_save, save_btn, watch=True)
    pn.serve(
        pn.Column(
            jsoneditor, pn.pane.JSON(jsoneditor.param.value, theme="light"), save_btn
        ).servable()
    )

    jsoneditor.get_value()
