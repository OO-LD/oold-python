
//import {Vue} from "https://esm.sh/vue@3";
import { createApp, ref } from "vue"; //"https://esm.sh/vue@3";
//import {Vue} from "https://unpkg.com/vue@3/dist/vue.global.js"
//import {JSONEditor} from "https://esm.sh/@json-editor/json-editor@latest"
//import {JSONEditor} from "@json-editor/json-editor"
//import {JSONEditor} from "jsoneditor"
import JsonEditorComponent from "@/jsoneditor.vue" //"jsoneditor.js"
import "@/jsoneditor_component.less"


//export function render() {
export function render({ model, el }) {
  const e = document.createElement('div')
  e.setAttribute("id", "jsoneditor-container")
  el.append(e);
  console.debug("Create App");
  //debugger
  let options = model.get("options");
  options = options || {
    "theme": 'bootstrap4',
    "iconlib": 'spectre',
    schema: {
      "title": "Editor Test",
      "required": ["test"],
      "properties": {"test": {"type": "string"}}},
    //   startval: this.data
  }
  const app = createApp(JsonEditorComponent, {
    options: options,
    onChange: (value) => {
      console.debug("CHANGE", value);
      /*
      * somehow also selection in the additional property list
      * are triggering this change event
      * filter values that are Event objects
      */
      if (!(value instanceof Event)) {
        model.set("value", value);
        model.save_changes();
      }
    },
    onReady: (value) => {
      console.debug("JSONEditor is ready");
      model.set("ready", value);
      model.save_changes();
    },
  });
  const root = app.mount(el);

  // event wiring from python to javascript
  model.on("change:value", () => {
    root.setValue(model.get("value"))
  });
  model.on("change:options", () => {
    root.setOptions(model.get("options"))
  });
  model.on("change:schema", () => {
    root.setSchema(model.get("schema"))
  });
}
