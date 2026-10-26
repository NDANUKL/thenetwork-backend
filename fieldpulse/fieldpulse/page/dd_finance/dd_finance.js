frappe.pages['dd-finance'].on_page_load = function(wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: __('Scout payments'), single_column: true});
  const body = $('<div class="p-4">').appendTo(page.main);
  page.add_field({fieldname:'request', label:__('Customer request'), fieldtype:'Link', options:'Diaspora Request', change:()=>load()});
  page.set_primary_action(__('New scout agreement'), ()=>frappe.new_doc('DD Scout Offer'));
  page.set_secondary_action(__('Refresh'), ()=>load());
  for (const dt of ['DD Scout Offer','DD Scout Payout','DD Scout Expense'])
    page.add_inner_button(__(dt.replace('DD ','')), ()=>frappe.set_route('List',dt), __('Records'));
  for (const dt of ['DD Task Budget','DD Finance Cost','DD Customer Refund','DD Finance Case','DD Finance Audit'])
    page.add_inner_button(__(dt.replace('DD ','')), ()=>frappe.set_route('List',dt), __('More'));
  const cash = (row, value)=>`${row.currency} ${Number(value || 0).toFixed(2)}`;
  function record(row) {
    const dialog = new frappe.ui.Dialog({title:__('Record successful payment'), fields:[
      {fieldname:'help',fieldtype:'HTML',options:'<p>'+__('Pay through your business bank or M-Pesa first. This form only records a successful transfer. Openfloat is optional. Use masked recipient details.')+'</p>'},
      {fieldname:'kind',label:__('Payment for'),fieldtype:'Select',options:'Earning\nTravel advance',default:row.status==='Awaiting work approval'?'Travel advance':'Earning',reqd:1},
      {fieldname:'amount',label:__('Amount in '+row.currency),fieldtype:'Currency',default:row.available,reqd:1},
      {fieldname:'channel',label:__('Paid through'),fieldtype:'Select',options:'Bank transfer\nBusiness M-Pesa\nPesapal / Openfloat',default:'Bank transfer',reqd:1},
      {fieldname:'reference',label:__('Successful transaction reference'),fieldtype:'Data',reqd:1},
      {fieldname:'payment_date',label:__('Actual payment date'),fieldtype:'Date',default:frappe.datetime.get_today(),reqd:1},
      {fieldname:'recipient',label:__('Actual recipient name and masked account / phone'),fieldtype:'Data',reqd:1},
      {fieldname:'evidence',label:__('Private transaction receipt'),fieldtype:'Data',read_only:1,reqd:1},
      {fieldname:'recipient_matches',label:__('I checked that this successful transfer paid this scout the recorded amount'),fieldtype:'Check',reqd:1}
    ], primary_action_label:__('Save payment'), primary_action:async values=>{
      dialog.get_primary_btn().prop('disabled',true);
      try {await frappe.call({method:'fieldpulse.finance.record_external_payment',args:{offer:row.offer,...values},freeze:true});dialog.hide();await load();}
      finally {dialog.get_primary_btn().prop('disabled',false);}
    }});
    const chooser=$('<input type="file" accept="image/jpeg,image/png,application/pdf">').appendTo(dialog.fields_dict.evidence.$wrapper);
    chooser.on('change',async event=>{
      const file=event.target.files[0];if(!file)return;
      const form=new FormData();form.append('file',file);form.append('is_private','1');
      try {
        const response=await fetch('/api/method/upload_file',{method:'POST',headers:{'X-Frappe-CSRF-Token':frappe.csrf_token},body:form});
        const result=await response.json();if(!response.ok||result.exc)throw new Error(__('Receipt upload failed'));
        dialog.set_value('evidence',result.message.file_url);
      } catch(error) {frappe.msgprint(error.message);}
    });
    dialog.show();
  }
  async function load() {
    body.empty().append($('<p>').text(__('Loading scout payments?')));
    try {
      const {message}=await frappe.call('fieldpulse.finance.scout_payments',{request:page.fields_dict.request.get_value()||undefined});
      body.empty().append($('<p class="text-muted">').text(__('Agree scout pay, approve the work, then record the successful external payment. Customer collections and settlements stay in Pesapal; bank access is not required for work approval.')));
      if(!message.items.length)body.append($('<p>').text(__('No accepted scout agreements yet. Create and issue an agreement; the scout accepts it in Earnings. A budget is optional.')));
      for(const row of message.items) {
        const panel=$('<section class="border rounded p-3 mb-3">').appendTo(body);
        $('<a>').attr('href','/app/dd-scout-offer/'+encodeURIComponent(row.offer)).text(row.scout+' ? '+(row.task||row.project)).appendTo(panel);
        $('<p>').text(row.status+' ? '+__('Due')+': '+(row.due_date||__('After work approval'))).appendTo(panel);
        $('<p>').text(__('Agreed fee')+': '+cash(row,row.agreed_fee)+' ? '+__('Paid')+': '+cash(row,Number(row.advances_paid)+Number(row.earning_payments))+' ? '+__('Remaining')+': '+cash(row,row.net_payable)).appendTo(panel);
        if(row.status==='Awaiting work approval')$('<p>').text(__('Awaiting work approval. Only agreed travel advances can be recorded.')).appendTo(panel);
        if(Number(row.reserved)>0)$('<p>').text(__('An existing payout has reserved')+' '+cash(row,row.reserved)+'. '+__('Resolve that payment before recording another.')).appendTo(panel);
        if(row.status!=='On hold'&&(Number(row.available)>0||Number(row.advance_available)>0))
          $('<button class="btn btn-primary btn-sm">').text(__('Record payment')).on('click',()=>record(row)).appendTo(panel);
      }
    } catch(error) {body.empty().append($('<p>').text(error.message||__('Scout payments are unavailable.')));}
  }
  wrapper.finance_load=load;wrapper.finance_page=page;
};
frappe.pages['dd-finance'].on_page_show=function(wrapper){if(frappe.route_options?.request){wrapper.finance_page.fields_dict.request.set_value(frappe.route_options.request);frappe.route_options=null;}wrapper.finance_load?.();};
