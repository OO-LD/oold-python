import { openBlock as a, createElementBlock as r, createElementVNode as n, toDisplayString as l } from "vue";
const d = (e, t) => {
  const s = e.__vccOpts || e;
  for (const [i, o] of t)
    s[i] = o;
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
}, h = {
  ref: "jsoneditor",
  id: "jsoneditor",
  class: "bootstrap-wrapper"
};
function p(e, t, s, i, o, c) {
  return a(), r("div", h, [
    n("h2", null, l(s.title), 1)
  ], 512);
}
const f = /* @__PURE__ */ d(_, [["render", p]]);
export {
  f as default
};
