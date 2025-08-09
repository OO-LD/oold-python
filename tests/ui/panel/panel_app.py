import panel as pn

from oold.ui.panel.anywidget_vite.jsoneditor import JsonEditor


class App(pn.viewable.Viewer):
    def __init__(self, **params):
        super().__init__(**params)

        self.jsoneditor = JsonEditor(max_height=500, max_width=800)

        self.save_btn = pn.widgets.Button(
            css_classes=["save_btn"], name="Save", button_type="primary"
        )
        pn.bind(self.on_save, self.save_btn, watch=True)

        self._view = pn.Column(
            self.jsoneditor,
            pn.pane.JSON(self.jsoneditor.param.value, theme="light"),
            self.save_btn,
        )

    def on_save(self, event):
        # Handle the save event here
        print("Save button clicked")
        print("Current value:", self.jsoneditor.get_value())
        # Update the schema or any other logic as needed
        self.jsoneditor.options = {
            **self.jsoneditor.options,
            "schema": {**self.jsoneditor.options["schema"], "title": "Updated Title"},
        }

    def __panel__(self):
        return self._view


if pn.state.served:
    pn.extension(sizing_mode="stretch_width")

    App().servable()

if __name__ == "__main__":
    pn.serve(App().servable())
