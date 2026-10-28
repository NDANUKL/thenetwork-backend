frappe.ui.form.on('DD Revisit Request', {
  refresh(frm) {
    frm.disable_save();
    frm.set_intro(__('Historical questionnaire revisit record. New visits must be allocated from an approved project Task Brief.'));
  }
});
