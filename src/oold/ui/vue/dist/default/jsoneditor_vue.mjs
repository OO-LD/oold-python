import { openBlock as r, createElementBlock as d, createElementVNode as l, toDisplayString as p, createApp as c } from "vue";
const h = (e, t) => {
  const s = e.__vccOpts || e;
  for (const [o, n] of t)
    s[o] = n;
  return s;
}, _ = {
  name: "dm-json-form3",
  components: {},
  props: {
    options: {
      type: Object
    },
    schema: {
      type: Object
    },
    data: {
      type: Object
    },
    enabled: {
      type: Boolean,
      default: !0
    },
    ready: {
      type: Boolean,
      default: !1
    },
    title: {
      type: String,
      default: ""
    }
  },
  methods: {
    init() {
      console.debug("init: ", this.$el), this.editor.on("ready", () => {
        console.debug("JSONEditor is ready"), this.$emit("ready", !0);
      }), this.editor.on("change", () => {
        let e = this.editor.getValue();
        e === "" && (e = null), this.$emit("change", e);
      });
    },
    setValue(e) {
      console.debug("setValue: ", e), this.editor ? this.editor.setValue(e) : console.warn("Editor not initialized yet, skipping data update");
    },
    setOptions(e) {
      console.debug("setOptions: ", e), this.editor && this.editor.destroy(), this._options = { ...this._options, ...e }, this.editor = new JSONEditor(this.$el, this._options), this.$emit("ready", !1), this.init();
    },
    setSchema(e) {
      console.debug("setSchema: ", e);
      var t = null;
      this.editor && (t = this.editor.getValue(), this.editor.destroy()), this._options = { ...this._options, schema: e, startval: t }, this.editor = new JSONEditor(this.$el, this._options), this.$emit("ready", !1), this.init();
    }
  },
  async mounted() {
    await import("jsoneditor"), this._options = { theme: "bootstrap4", iconlib: "spectre", remove_button_labels: !0, ajax: !0, ajax_cache_responses: !1, disable_collapse: !1, disable_edit_json: !0, disable_properties: !1, use_default_values: !0, required_by_default: !1, display_required_only: !0, show_opt_in: !1, show_errors: "always", disable_array_reorder: !1, disable_array_delete_all_rows: !1, disable_array_delete_last_row: !1, keep_oneof_values: !1, no_additional_properties: !0, case_sensitive_property_search: !1, ...this.options }, console.debug("Options: ", this._options), this.editor = new JSONEditor(this.$el, this._options), console.debug("Editor: ", this.editor), this.init();
  },
  emits: ["onChange", "onReady"]
}, u = {
  ref: "jsoneditor",
  id: "jsoneditor",
  class: "bootstrap-wrapper"
};
function f(e, t, s, o, n, a) {
  return r(), d("div", u, [
    l("h2", null, p(s.title), 1)
  ], 512);
}
const y = /* @__PURE__ */ h(_, [["render", f]]);
function b({ model: e, el: t }) {
  const s = document.createElement("div");
  s.setAttribute("id", "jsoneditor-container"), t.append(s), console.debug("Create App");
  let o = e.get("options");
  o = o || {
    theme: "bootstrap4",
    iconlib: "spectre",
    schema: {
      title: "Editor Test",
      required: ["test"],
      properties: { test: { type: "string" } }
    }
    //   startval: this.data
  };
  const a = c(y, {
    options: o,
    onChange: (i) => {
      console.debug("CHANGE", i), i instanceof Event || (e.set("value", i), e.save_changes());
    },
    onReady: (i) => {
      console.debug("JSONEditor is ready"), e.set("ready", i), e.save_changes();
    }
  }).mount(t);
  e.on("change:value", () => {
    a.setValue(e.get("value"));
  }), e.on("change:options", () => {
    a.setOptions(e.get("options"));
  }), e.on("change:schema", () => {
    a.setSchema(e.get("schema"));
  });
}
export {
  b as render
};
