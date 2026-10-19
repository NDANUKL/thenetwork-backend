frappe.listview_settings["Field Task"] = {
  add_fields: ["status", "submission_review_status", "submission_review_reasons"],
  formatters: {
    submission_review_status(value, df, doc) {
      const escape = frappe.utils.escape_html;
      return `<span>${escape(value || "Awaiting submission")}</span>${doc.submission_review_reasons ? `<br><small title="${escape(doc.submission_review_reasons)}">${escape(doc.submission_review_reasons)}</small>` : ""}`;
    }
  }
};
