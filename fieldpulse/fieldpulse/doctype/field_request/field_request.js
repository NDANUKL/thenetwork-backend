if (frappe.boot.dd_native_handover_active) {
// DD Alignment Project Form
frappe.ui.form.on("Field Request", {
  refresh(frm) {
    if (!frm.doc.diaspora_request) return;
    ["source", "source_reference", "diaspora_request", "request_type", "county", "field_brief", "project_number", "project_title", "project_key", "evidence_requirements", "customer_target_date", "deadline_preference", "status"].forEach(field => frm.set_df_property(field, "read_only", 1));
    frm.set_df_property("source_reference", "hidden", 1);
    frm.set_df_property("dd_site_locations", "hidden", 1);
    frm.set_df_property("deadline", "label", "Agreed work deadline");
    frm.set_df_property("deadline", "description", "Copied to the scout task's Due date. Confirm this date when arranging the work.");
    frm.set_intro(frm.doc.alignment_review ? "This project's scope needs review. Ask the customer for details from the linked Diaspora Request." : "Verify the locations below before assigning scouts. Customer scope and county are taken from the submission.", frm.doc.alignment_review ? "orange" : "blue");
  },
});


// DD Project Scout Assignment
frappe.ui.form.on("Field Request", {
  refresh(frm) {
    frm.remove_custom_button(__("Assign scouts"));
    frm.set_df_property("priority", "description", "");
    frm.set_df_property("deadline", "description", "");
    frm.set_df_property("status", "description", __("Use Assign scouts to select a Scout Profile and create their Field Task. Changing status alone does not assign a scout."));
    if (frm.doc.alignment_review) frm.set_intro("Confirm each project's scope and county before assigning scouts.", "orange");
    if (frm.is_new() || ["Completed", "Cancelled"].includes(frm.doc.status) || !frm.perm.some(p => p.write)) return;
    frm.add_custom_button(__("Assign scouts"), () => {
      if (frm.is_dirty()) {
        frappe.msgprint(__("Save this project before assigning scouts."));
        return;
      }
      if (!frm.doc.project_number || frm.doc.alignment_review || !frm.doc.county) {
        frappe.msgprint(__("Confirm this project's scope, project number and county before assigning scouts."));
        return;
      }
      const dialog = new frappe.ui.Dialog({
        title: __("Assign scouts to this project"),
        fields: [{ fieldname: "assignment_help", fieldtype: "HTML", options: `<p>${__("Choose a scout in the row below. Use Add Row for more scouts.")}</p>` },
          { fieldname: "assignments", label: __("Scout assignments"), fieldtype: "Table", reqd: 1, in_place_edit: true, data: [{}],
          fields: [
            { fieldname: "scout", label: __("Scout"), fieldtype: "Link", options: "Scout Profile", reqd: 1, in_list_view: 1,
              async onchange() {
                const row = this.doc;
                if (!row) return;
                const selected = row.scout;
                row.scout_name = "";
                row.base_county = "";
                dialog.fields_dict.assignments.grid.refresh();
                if (!selected) return;
                const result = await frappe.db.get_value("Scout Profile", selected, ["scout_name", "base_county"]);
                if (row.scout !== selected) return;
                row.scout_name = result.message?.scout_name || "";
                row.base_county = result.message?.base_county || __("County unconfirmed");
                dialog.fields_dict.assignments.grid.refresh();
              },
            },
            { fieldname: "scout_name", label: __("Full name"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
            { fieldname: "base_county", label: __("County"), fieldtype: "Data", read_only: 1, in_list_view: 1 },
            { fieldname: "questionnaire", label: __("Questionnaire"), fieldtype: "Link", options: "FP Questionnaire" },
          ] }],
        primary_action_label: __("Assign"),
        async primary_action(values) {
          dialog.disable_primary_action();
          try {
            const result = await frappe.call({ method: "dd_assign_scouts_without_extra_columns", args: { field_request: frm.doc.name, assignments: JSON.stringify(values.assignments) }, freeze: true });
            dialog.hide();
            frappe.msgprint(__("Scout tasks: {0}", [result.message.tasks.join(", ")]));
            await frm.reload_doc();
          } finally { dialog.enable_primary_action(); }
        },
      });
      dialog.show();
    });
  },
});


}

frappe.ui.form.on("Field Request", {
  setup(frm) {
    frm.set_query("question", "scout_checks", () => ({filters: {questionnaire: frm.doc.scout_questionnaire, active: 1, question_group: "Service"}}));
  },
  scout_service(frm) {
    if (!frm.doc.scout_service) return;
    frm.set_value("scout_questionnaire", null);
    frm.clear_table("scout_checks");
    frm.set_value("scout_checks_confirmed", 0);
    frm.refresh_field("scout_checks");
    frm.set_intro(__("Save to load this service template, then review its selected checks before confirming dispatch."));
  }
});
