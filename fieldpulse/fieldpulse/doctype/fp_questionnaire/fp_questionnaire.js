frappe.ui.form.on("FP Questionnaire", {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__("View questions"), () => {
      frappe.route_options = {questionnaire: frm.doc.name};
      frappe.set_route("List", "FP Question");
    });
    if (frm.doc.status === "Published" && frm.perm.some(p => p.create)) frm.add_custom_button(__("Create new version"), async () => {
      const {message} = await frappe.call("fieldpulse.fieldpulse.doctype.fp_questionnaire.fp_questionnaire.create_new_version", {questionnaire_code: frm.doc.questionnaire_code});
      frappe.set_route("Form", "FP Questionnaire", message.new_questionnaire);
    });
  }
});
