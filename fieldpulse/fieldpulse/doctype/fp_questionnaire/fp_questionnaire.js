frappe.ui.form.on('FP Questionnaire', {
  refresh(frm) { frm.disable_save(); frm.set_intro(__('Historical questionnaire record. New assignments use Task Briefs.')); }
});
