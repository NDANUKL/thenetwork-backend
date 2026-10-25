frappe.ui.form.on('DD Revisit Request', {
  assignment_choice(frm) {if(frm.doc.assignment_choice==='Same scout'){frm.set_value('replacement_scout',null);frm.set_value('reassignment_reason',null);}},
  refresh(frm) {
    frm.set_intro(__('Record who funds this revisit and the contract, client acceptance where required, and scout compensation references. Authorization does not charge the client or deduct scout pay. Only Dispatch creates fieldwork and notifies the scout.'));
    const pending = frm.doc.status === 'Awaiting authorization';
    for (const field of ['assignment_choice','replacement_scout','reassignment_reason','scope_category','cost_arrangement','contract_reference','client_acceptance_reference','scout_compensation_reference','authorization_notes']) frm.set_df_property(field,'read_only',!pending);
    if (frm.is_new() || !['System Manager','Field Operations Coordinator'].some(role => frappe.user.has_role(role))) return;
    async function act(action, notes) {
      if (frm.is_dirty()) await frm.save();
      const {message} = await frappe.call({method:'fieldpulse.revisit_authorization.act',args:{revisit:frm.doc.name,action,notes},freeze:true});
      await frm.reload_doc();
      if (action === 'Dispatch') frappe.set_route('Form','Field Task',message.task);
    }
    if (pending) frm.add_custom_button(__('Authorize'),()=>act('Authorize'));
    if (frm.doc.status === 'Authorized') frm.add_custom_button(__('Dispatch'),()=>act('Dispatch'));
    const revisionAction = frm.doc.status === 'Authorized' ? 'Return for changes' : ['Declined','Cancelled'].includes(frm.doc.status) ? 'Reopen' : null;
    if (revisionAction) frm.add_custom_button(__(revisionAction),()=>frappe.prompt({fieldname:'notes',label:__('Reason for renewed review'),fieldtype:'Small Text',reqd:1},({notes})=>act(revisionAction,notes),__(revisionAction)));
    if (['Awaiting authorization','Authorized'].includes(frm.doc.status)) {
      for (const action of ['Decline','Cancel']) frm.add_custom_button(__(action),()=>frappe.prompt({fieldname:'notes',label:__('Reason'),fieldtype:'Small Text',reqd:1},({notes})=>act(action,notes),__(action)));
    }
  }
});
