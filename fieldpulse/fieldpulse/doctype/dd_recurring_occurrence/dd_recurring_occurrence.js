frappe.ui.form.on('DD Recurring Occurrence', {
  refresh(frm) {
    if (frm.is_new() || !frappe.user_roles.some(role => ['System Manager','Field Operations Coordinator'].includes(role))) return;
    frm.add_custom_button(__('Open plan'), () => frappe.set_route('Form','DD Recurring Plan',frm.doc.plan));
    if (frm.doc.request) frm.add_custom_button(__('Open visit request'), () => frappe.set_route('Form','Diaspora Request',frm.doc.request));
    if (['Scheduled','Awaiting access','Access confirmed'].includes(frm.doc.status)) {
      const actions=frm.doc.status==='Access confirmed' ? ['Prepare','Skip'] : ['Skip'];
      for (const action of actions) frm.add_custom_button(__(action), () => {
        const dialog=new frappe.ui.Dialog({ title:__(action+' recurring visit'),fields:[{fieldname:'notes',fieldtype:'Small Text',label:__('Notes / skip reason'),reqd:action==='Skip'}],primary_action_label:__(action),primary_action:async values => {
          dialog.disable_primary_action();
          try { await frappe.call({method:'fieldpulse.recurring.review',args:{plan:frm.doc.plan,occurrence:frm.doc.name,action,notes:values.notes||'',expected_modified:frm.doc.modified,submission_id:dialog.action_id}});dialog.hide();await frm.reload_doc(); }
          finally { dialog.enable_primary_action(); }
        }});dialog.action_id=crypto.randomUUID();dialog.show();
      },__('Visit actions'));
    }
  }
});
