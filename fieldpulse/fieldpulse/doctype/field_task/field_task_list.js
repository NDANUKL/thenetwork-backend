frappe.listview_settings["Field Task"] = {
  hide_name_column: true,
  hide_name_filter: true,
  add_fields: ["project_title", "request_type", "field_request", "scout_profile", "status", "submission_review_status", "submission_review_reasons"],
  formatters: {
    project_title(value, df, doc) {
      return frappe.utils.escape_html(value || doc.request_type || __("Fieldwork task"));
    },
    submission_review_status(value, df, doc) {
      const escape = frappe.utils.escape_html;
      return `<span>${escape(value || "Awaiting submission")}</span>${doc.submission_review_reasons ? `<br><small title="${escape(doc.submission_review_reasons)}">${escape(doc.submission_review_reasons)}</small>` : ""}`;
    }
  }
};
