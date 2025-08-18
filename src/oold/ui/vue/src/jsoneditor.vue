<template>
  <div ref="jsoneditor" id="jsoneditor" class="bootstrap-wrapper">
    <h2>{{title}}</h2>

  </div>
</template>

<script>

export default {
  name: 'dm-json-form3',
  components: {},

  props: {
    options: {
      type: Object,
    },
    schema: {
      type: Object,
    },
    data: {
      type: Object,
    },
    enabled: {
      type: Boolean,
      default: true
    },
    ready: {
      type: Boolean,
      default: false
    },
    title: {
      type: String,
      default: ""
    },
  },

  methods: {
    init() {
      console.debug("init: ", this.$el);
      this.editor.on('ready', () => {
        // Now the api methods will be available
        console.debug("JSONEditor is ready");
        this.$emit('ready', true)
      });

      this.editor.on('change' , () => {
        let value = this.editor.getValue();
        // handle empty value of schema is empty
        if (value === "") value = null;
        this.$emit('change' , value)
      })
    },
    setValue(val) {
      console.debug("setValue: ", val);
      if (this.editor) {
        this.editor.setValue(val);
      } else {
        console.warn("Editor not initialized yet, skipping data update")
      }
    },
    setOptions(options) {
      console.debug("setOptions: ", options);
      if (this.editor) {
        this.editor.destroy();
      }
      this._options = {...this._options, ...options}
      this.editor = new JSONEditor(this.$el, this._options);
      this.$emit('ready', false)
      this.init();
    },
    setSchema(schema) {
      console.debug("setSchema: ", schema);
      var startval = null;
      if (this.editor) {
        // keep the current value if the editor is already initialized
        startval = this.editor.getValue();
        this.editor.destroy();
      }
      this._options = {...this._options, schema: schema, startval: startval};
      this.editor = new JSONEditor(this.$el, this._options);
      this.$emit('ready', false)
      this.init();
    },
  },

  async mounted() {
    await import("jsoneditor");

    // default options
    this._options = {...{
      "theme": "bootstrap4",
      "iconlib": "spectre",
      "remove_button_labels": true,
      "ajax": true,
      "ajax_cache_responses": false,
      "disable_collapse": false,
      "disable_edit_json": true,
      "disable_properties": false,
      "use_default_values": true,
      "required_by_default": false,
      "display_required_only": true,
      "show_opt_in": false,
      "show_errors": "always",
      "disable_array_reorder": false,
      "disable_array_delete_all_rows": false,
      "disable_array_delete_last_row": false,
      "keep_oneof_values": false,
      "no_additional_properties": true,
      "case_sensitive_property_search": false,
      //"form_name_root": "this.jsonschema.getSchema().id",
      //"user_language": "this.config.lang"
    }, ...this.options}

    console.debug("Options: ", this._options)
    this.editor = new JSONEditor(this.$el, this._options);
    console.debug("Editor: ", this.editor)

    this.init();

  },

  emits: ['onChange', 'onReady'],
};
</script>

<!-- <style lang="less">
.bootstrap-wrapper {
  @import (less) url('https://cdn.jsdelivr.net/npm/bootstrap@4.6.1/dist/css/bootstrap.min.css');
}
</style> -->
