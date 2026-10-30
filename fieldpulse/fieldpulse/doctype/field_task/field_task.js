frappe.ui.form.on("Field Task", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__("County assignment balance"), () => frappe.set_route("query-report", "County Assignment Balance", {field_request: frm.doc.field_request}));
    frm.add_custom_button(__("Review scout submission"), async () => {
      const rows = await frappe.db.get_list("FP Task Response", {filters: {task: frm.doc.name, status: "Submitted"}, fields: ["name"], order_by: "creation desc", limit: 1});
      if (!rows.length) return frappe.msgprint(__("No submitted response is available yet."));
      frappe.set_route("Form", "FP Task Response", rows[0].name);
    });
  }
});
