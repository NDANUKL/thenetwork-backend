frappe.ui.form.on('DD Recurring Plan', {
  refresh(frm) {
    if (frm.is_new()) return;
    frm.add_custom_button(__('Visit schedule'), () => frappe.set_route('List', 'DD Recurring Occurrence', { plan: frm.doc.name }));
    if (!frappe.user_roles.some(role => ['System Manager','Field Operations Coordinator'].includes(role))) return;
    const actions = { 'Pending review':['Approve','Decline','Cancel'], Active:['Pause','Cancel'], Paused:['Resume','Cancel'] };
    for (const action of actions[frm.doc.status] || []) frm.add_custom_button(__(action), () => {
      const dialog = new frappe.ui.Dialog({ title: __(action + ' recurring plan'), fields: [
        { fieldtype:'HTML', options:'<p>Each visit needs a separate quotation, accepted price, verified deposit and confirmed access before scout dispatch. Cancellation stops unprepared visits; it does not cancel existing visit requests or financial obligations.</p>' },
        { fieldname:'notes', fieldtype:'Small Text', label:__('Decision / schedule and commercial review'), reqd:['Approve','Decline'].includes(action) },
      ], primary_action_label:__(action), primary_action:async values => {
        dialog.disable_primary_action();
        try { await frappe.call({ method:'fieldpulse.recurring.review',args:{ plan:frm.doc.name,action,notes:values.notes || '',expected_modified:frm.doc.modified,submission_id:dialog.action_id } });dialog.hide();await frm.reload_doc(); }
        finally { dialog.enable_primary_action(); }
      }});
      dialog.action_id=crypto.randomUUID();dialog.show();
    }, __('Plan actions'));
    frm.set_intro(__('Review the frozen scope, all visit dates and the per-visit payment arrangement before approving. No automatic renewal or automatic charging.'), 'blue');
  }
});
