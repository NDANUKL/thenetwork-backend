/* Finance records describe obligations and manually reconciled payments. No button sends money. */
window.fieldpulse_finance_form = function (frm) {
  const allowed = ['Finance', 'System Manager'].some(role => frappe.user.has_role(role));
  if (!allowed || frm.is_new()) return;
  const dt=frm.doctype, state=frm.doc.status;
  if(dt==='DD Payout Beneficiary') ['scout','method','account_holder','institution','account_number'].forEach(field=>frm.set_df_property(field,'read_only',1));
  // Financial evidence always uploads privately; do not offer a public-file toggle.
  for(const field of Object.values(frm.fields_dict))if(field.df.fieldtype==='Attach'&&!field.df.read_only){
    field.on_attach_click=()=>{
      if(frm.is_new()){frappe.msgprint(__('Save the draft before attaching private evidence.'));return;}
      const chooser=document.createElement('input');chooser.type='file';chooser.accept='image/jpeg,image/png,application/pdf';
      chooser.onchange=async()=>{const file=chooser.files[0];if(!file)return;const data=new FormData();data.append('file',file);data.append('is_private','1');data.append('doctype',frm.doctype);data.append('docname',frm.doc.name);data.append('fieldname',field.df.fieldname);try{const response=await fetch('/api/method/upload_file',{method:'POST',headers:{'X-Frappe-CSRF-Token':frappe.csrf_token},body:data});const result=await response.json();if(!response.ok||result.exc)throw new Error(__('Private upload failed'));await frm.set_value(field.df.fieldname,result.message.file_url);await frm.save();}catch(error){frappe.msgprint(error.message);}};chooser.click();
    };
    field.on_attach_doc_image=field.on_attach_click;
  }
  const notes={fieldname:'notes',label:__('Decision / reconciliation notes'),fieldtype:'Small Text',reqd:1};
  const proof={fieldname:'evidence',label:__('Private confirmation evidence attached to this record'),fieldtype:'Data',read_only:1,reqd:1};
  const alternative={fieldname:'accept_alternative',label:__('I authorise the recorded alternative evidence instead of a receipt'),fieldtype:'Check'};
  const run=(action,fields=[])=>frm.add_custom_button(__(action),()=>{
    const perform=async values=>{
      if(values.evidence&&!values.evidence.startsWith('/private/files/')){frappe.msgprint(__('Upload confirmation evidence as a private file.'));return;}
      
      const data={...values};for(const key of ['accept_alternative','provider_checked','recipient_matches','failure_confirmed'])if(key in data)data[key]=!!data[key];
      await frappe.call({method:'fieldpulse.finance_actions.act',args:{doctype:dt,name:frm.doc.name,action,data},freeze:true});await frm.reload_doc();
    };
    if(fields.length){
      const dialog=new frappe.ui.Dialog({title:__(action),fields,primary_action_label:__('Record action'),primary_action:async values=>{await perform(values);dialog.hide();}});
      if(fields.some(field=>field.fieldname==='evidence')){
        const chooser=$('<input type="file" accept="image/jpeg,image/png,application/pdf">').appendTo(dialog.fields_dict.evidence.$wrapper);
        chooser.on('change',async event=>{
          const file=event.target.files[0];if(!file)return;
          const form=new FormData();form.append('file',file);form.append('is_private','1');form.append('doctype',dt);form.append('docname',frm.doc.name);
          try{const response=await fetch('/api/method/upload_file',{method:'POST',headers:{'X-Frappe-CSRF-Token':frappe.csrf_token},body:form});const result=await response.json();if(!response.ok||result.exc)throw new Error(__('Private upload failed'));dialog.set_value('evidence',result.message.file_url);}catch(error){frappe.msgprint(error.message);}
        });
      }
      dialog.show();
    }else void perform({});
  },__('Finance actions'));
  if(dt==='DD Scout Offer'){
    if(state==='Draft')run('Issue');
    if(state==='Accepted'&&!frm.doc.task)run('Bind existing assignment',[{fieldname:'task',label:__('Existing assignment for this scout/project'),fieldtype:'Link',options:'Field Task',reqd:1},notes]);
    if(['Draft','Issued','Accepted'].includes(state)&&!frm.doc.task)run('Withdraw',[notes]);
  }
  if(dt==='DD Scout Expense'&&state==='Submitted'){run('Approve',[notes,alternative]);run('Reject',[notes]);}
  if(dt==='DD Earning Adjustment'&&state==='Draft')run('Approve',[notes,alternative]);
  if(dt==='DD Payout Beneficiary')frm.add_custom_button(__('View recipient after verification'),()=>frappe.prompt([{fieldname:'password',label:__('Your password'),fieldtype:'Password',reqd:1}],async values=>{const result=await frappe.call('fieldpulse.finance.reveal_beneficiary',{beneficiary:frm.doc.name,password:values.password});frappe.msgprint(frappe.utils.escape_html([result.message.account_holder,result.message.institution,result.message.account_number].join(' | ')));}));
  if(dt==='DD Payout Beneficiary'&&state==='Pending verification'){run('Verify',[notes,alternative]);run('Reject',[notes]);}
  if(dt==='DD Scout Payout'){
    frm.set_intro(__('Record the money movement in the approved business channel. Use {0} as your business reference. These actions only record approval and actual outcomes.',[frm.doc.name]));
    if(state==='Draft'){run('Independent review',[notes]);run('Approve');}
    if(state==='Approved')run('Begin processing');
    if(['Processing','On hold'].includes(state)){
      run('Confirm paid',[{fieldname:'reference',label:__('Actual successful transaction / reversal reference'),fieldtype:'Data',reqd:1},{fieldname:'actual_amount',label:__('Actual confirmed amount in '+frm.doc.currency),fieldtype:'Currency',reqd:1},proof,{fieldname:'recipient_matches',label:__('I verified the actual recipient matches the frozen recipient and amount'),fieldtype:'Check',reqd:1},notes]);
      run('Confirm failed',[proof,{fieldname:'failure_confirmed',label:__('The provider confirms failure / no money movement; this is not a timeout or uncertain outcome'),fieldtype:'Check',reqd:1},notes]);
    }
    if(['Approved','Processing','On hold'].includes(state))run('Hold',[notes]);
    if(['Draft','Approved'].includes(state))run('Cancel before execution',[notes]);
  }
  if(dt==='DD Finance Cost'&&state==='Draft')run('Approve',[notes,alternative]);
  if(dt==='DD Customer Refund'){
    frm.set_intro(__('One refund case per original payment. Provider receipt of a request is not a completed refund. Check Pesapal and preserve its original recipient/currency.'));
    if(state==='Requested'){run('Independent review',[notes]);run('Approve',[notes,{fieldname:'provider_checked',label:__('I checked the original method, current merchant refund rules and any existing refund/chargeback'),fieldtype:'Check',reqd:1}]);}
    if(state==='Approved')run('Record provider pending',[{fieldname:'reference',label:__('Provider case/request reference'),fieldtype:'Data',reqd:1},notes]);
    if(state==='Provider pending'){
      run('Confirm refund',[proof,{fieldname:'actual_amount',label:__('Actual refunded amount in '+frm.doc.currency),fieldtype:'Currency',reqd:1},{fieldname:'recipient_matches',label:__('I reconciled success to the original / explicitly approved repayment recipient'),fieldtype:'Check',reqd:1},{fieldname:'credit_reference',label:__('Accounting credit document reference'),fieldtype:'Data',reqd:1},{fieldname:'service_component',label:__('Service revenue credited, excluding tax'),fieldtype:'Currency',reqd:1},{fieldname:'conversion_rate',label:__('Recorded units of reporting currency per unit, if different'),fieldtype:'Float'},{fieldname:'rate_date',label:__('Conversion-rate date, if different'),fieldtype:'Date'},notes]);
      run('Confirm failed',[proof,{fieldname:'failure_confirmed',label:__('Actual failure is confirmed; this is not merely a pending request'),fieldtype:'Check',reqd:1},notes]);
    }
  }
  if(dt==='DD Finance Case'){
    if(state==='Proposed')run('Approve',[notes]);
    if(state==='Approved'){
      run('Close',[notes]);
      run('Approve compensation',[{fieldname:'offer',label:__('Accepted arrangement without an existing entitlement'),fieldtype:'Link',options:'DD Scout Offer',reqd:1},{fieldname:'fee',label:__('Explicit agreed fee compensation'),fieldtype:'Currency',reqd:1},{fieldname:'travel',label:__('Explicit agreed travel compensation'),fieldtype:'Currency'},proof,notes]);
    }
  }
  if(dt==='DD Scout Earning'){run(frm.doc.on_hold?'Release hold':'Hold',[notes]);}
};

// Cost planning is a separate form; the simplified scout assignment dialog is preserved.
frappe.ui.form.on('Field Request',{refresh(frm){if(!frm.is_new()&&['Finance','System Manager'].some(role=>frappe.user.has_role(role)))frm.add_custom_button(__('Finance and scout arrangements'),()=>frappe.set_route('dd-finance',{request:frm.doc.diaspora_request}),__('Finance'));}});
frappe.ui.form.on('DD Revisit Request',{refresh(frm){if(!frm.is_new()&&['Finance','System Manager'].some(role=>frappe.user.has_role(role)))frm.add_custom_button(__('Review revisit costs'),()=>frappe.set_route('dd-finance',{request:frm.doc.request}),__('Finance'));}});
