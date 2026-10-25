if (frappe.boot.dd_native_handover_active) {
// DD Alignment Forms
frappe.ui.form.on("Diaspora Request", {
  refresh(frm) {
    frm.remove_custom_button(__("Assign scouts"));
    frm.set_df_property("status", "hidden", 1);
    frm.set_df_property("status", "read_only", 1);
    frm.set_df_property("customer_sites", "read_only", 0);
    const locations = frm.fields_dict.customer_sites?.grid;
    if (locations) {
      locations.cannot_add_rows = true;
      locations.cannot_delete_rows = true;
      locations.docfields.forEach(field => {
        if (field.fieldname) locations.update_docfield_property(field.fieldname, "read_only", field.fieldname === "location_verified" ? 0 : 1);
      });
      locations.refresh();
    }
    frm.set_df_property("customer_sites", "description", __("Review the destination and access arrangements, tick Location verified for each site, then save. Confirmation carries through to the linked projects."));
    if (!frm.is_new()) frm.add_custom_button(__("Project field requests"), () => frappe.set_route("List", "Field Request", { diaspora_request: frm.doc.name }));
  },
});


// DD Quotation Actions
frappe.ui.form.on("Diaspora Request", { refresh(frm) { if (!frm.is_new() && frm.perm.some(p => p.write)) { frm.add_custom_button("Prepare quotation", () => frappe.new_doc("DD Quotation", {request:frm.doc.name})); frm.add_custom_button("Quotations", () => frappe.set_route("List", "DD Quotation", {request:frm.doc.name})); } } });

// DD Request Details Actions
frappe.ui.form.on("Diaspora Request", {
  refresh(frm) {
    if (frm.is_new() || !frm.doc.dd_customer_account) return;
    if (!["System Manager", "Field Operations Coordinator", "Administrator"].some(role => frappe.user_roles.includes(role))) return;
    frm.add_custom_button("Ask for details", () => frappe.new_doc("DD Request Details", { request: frm.doc.name, status: "Draft" }));
    frm.add_custom_button("Details history", () => frappe.set_route("List", "DD Request Details", { request: frm.doc.name }));
  }
});

}

frappe.ui.form.on("Diaspora Request", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__("Scout submissions"), () => {
      frappe.route_options = {status: "Submitted"};
      frappe.set_route("List", "FP Task Response");
    });
    if (frm.doc.status === "Completed") frm.add_custom_button(__("Prepare client report"), async () => {
      const {message} = await frappe.call("fieldpulse.scout_reports.prepare_report", {reference: frm.doc.name});
      frappe.set_route("Form", "DD Service Report", message.report);
    });
  }
});
