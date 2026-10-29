frappe.listview_settings["Field Request"] = {
  add_fields: ["field_brief", "project_title"],
  formatters: {
    name(value, df, doc) {
      return `<a href="/app/field-request/${encodeURIComponent(value || '')}" title="${frappe.utils.escape_html(doc.field_brief || '')}">${frappe.utils.escape_html(value || '')}</a>`;
    }
  }
};
