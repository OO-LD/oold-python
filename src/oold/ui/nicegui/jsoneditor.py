from typing import Dict, Optional, Type, Union

from nicegui.element import Element
from nicegui.events import GenericEventArguments, Handler, handle_event
from typing_extensions import Self

from oold.model import LinkedBaseModel
from oold.model.v1 import LinkedBaseModel as LinkedBaseModel_v1


# class JsonEditor(ui.element,
class JsonEditor(
    Element,
    component="../vue/src/jsoneditor.vue",
    dependencies=["../vue/node_modules/@json-editor/json-editor/dist/jsoneditor.js"],
):
    def __init__(
        self,
        options: Optional[Dict] = None,
        on_change: Optional[Handler[GenericEventArguments]] = None,
    ) -> None:
        """JsonEditor

        An element that integrates the `JSON-SCHEMA form generator library
        <https://github.com/json-editor/json-editor>`.
        """
        super().__init__()
        self._props["options"] = options or {
            # "theme": 'tailwind',
            "theme": "bootstrap4",
            # "iconlib": 'spectre',
            "schema": {
                "required": ["test"],
                "properties": {"test": {"type": "string"}},
            },
            # "startval": {}
        }

        self._change_handlers = [on_change] if on_change else []

        self.on("change", self.handle_change)

    def handle_change(self, e: GenericEventArguments) -> None:
        for handler in self._change_handlers:
            handle_event(handler, e)

    def on_change(self, callback: Handler[GenericEventArguments]) -> Self:
        """Add a callback to be invoked when the user touches the joystick."""
        self._change_handlers.append(callback)
        return self

    # def clear(self):
    #    """Clear the signature."""
    #    self.run_method('clear')


class OswEditor(JsonEditor):
    def __init__(
        self,
        options: Optional[Dict] = None,
        on_change: Optional[Handler[GenericEventArguments]] = None,
        entity: Union[Type[LinkedBaseModel], Type[LinkedBaseModel_v1]] = None,
    ) -> None:
        options = options or {
            # "theme": 'tailwind',
            "theme": "bootstrap4",
            # "iconlib": 'spectre',
            "schema": {
                "required": ["test"],
                "properties": {"test": {"type": "string"}},
            },
            # "startval": {}
        }
        if entity is not None:
            options["schema"] = entity.export_schema()
        self.entity = entity
        super().__init__(options, on_change)

    def handle_change(self, e: GenericEventArguments) -> None:
        print(e)
        try:
            self.entity(**e.args)
        except Exception as ex:
            print("No valid instance: ", ex)
        super().handle_change(e)
