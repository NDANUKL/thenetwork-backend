frappe.ui.form.on("Field Request", {
  refresh(frm) {
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
      if ((frm.doc.diaspora_request && !frm.doc.project_number) || frm.doc.alignment_review || !frm.doc.county) {
        frappe.msgprint(__("Confirm this project's scope, project number and county before assigning scouts."));
        return;
      }
      const dialog = new frappe.ui.Dialog({
        title: __("Assign scouts to this project"),
        fields: [{ fieldname: "assignment_help", fieldtype: "HTML", options: `<p>${__("Choose a scout in the row below. Use Add Row for more scouts and give each scout a responsibility.")}</p>` },
          { fieldname: "assignments", label: __("Scout assignments"), fieldtype: "Table", reqd: 1, in_place_edit: true, data: [{}],
          fields: [
            { fieldname: "scout", label: __("Scout"), fieldtype: "Link", options: "Scout Profile", reqd: 1, in_list_view: 1 },
            { fieldname: "responsibility", label: __("Responsibility"), fieldtype: "Small Text", in_list_view: 1 },
            { fieldname: "location", label: __("Location"), fieldtype: "Link", options: "FP Location", in_list_view: 1 },
            { fieldname: "questionnaire", label: __("Questionnaire"), fieldtype: "Link", options: "FP Questionnaire" },
          ] }],
        primary_action_label: __("Assign"),
        async primary_action(values) {
          dialog.disable_primary_action();
          try {
            const result = await frappe.call({ method: "fieldpulse.project_alignment.assign_project_scouts", args: { field_request: frm.doc.name, assignments: JSON.stringify(values.assignments) }, freeze: true });
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
