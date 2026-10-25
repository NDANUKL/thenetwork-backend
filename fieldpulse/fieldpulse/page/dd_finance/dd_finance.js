frappe.pages['dd-finance'].on_page_load = function(wrapper) {
  const page=frappe.ui.make_app_page({parent:wrapper,title:__('Scout Finance'),single_column:true});
  const body=$('<div class="p-4"></div>').appendTo(page.main);
  const esc=value=>frappe.utils.escape_html(String(value??''));
  const link=(dt,name)=>`<a href="/app/${frappe.router.slug(dt)}/${encodeURIComponent(name)}">${esc(name)}</a>`;
  page.add_field({fieldname:'request',label:__('Customer request'),fieldtype:'Link',options:'Diaspora Request',change:()=>load()});
  for(const dt of ['DD Task Budget','DD Scout Offer','DD Scout Payout','DD Finance Cost','DD Customer Refund','DD Finance Case']){
    page.add_inner_button(__(dt.replace('DD ','')),()=>frappe.new_doc(dt),__('New record'));
    page.add_inner_button(__(dt.replace('DD ','')),()=>frappe.set_route('List',dt),__('Records'));
  }
  page.set_secondary_action(__('Refresh'),()=>load());
  page.add_inner_button(__('Request payment recipient'),()=>frappe.prompt([
    {fieldname:'scout',label:__('Scout'),fieldtype:'Link',options:'Scout Profile',reqd:1},
    {fieldname:'method',label:__('Payment method'),fieldtype:'Select',options:'M-Pesa\nBank',reqd:1},
    {fieldname:'account_holder',label:__('Account holder'),fieldtype:'Data',reqd:1},
    {fieldname:'institution',label:__('Bank / operator'),fieldtype:'Data',reqd:1},
    {fieldname:'account_number',label:__('Actual phone / account'),fieldtype:'Data',reqd:1},
    {fieldname:'password',label:__('Your login password'),fieldtype:'Password',reqd:1}
  ],async values=>{const result=await frappe.call('fieldpulse.finance.request_beneficiary',values);frappe.set_route('Form','DD Payout Beneficiary',result.message.name);},__('Recipient verification request')));
  async function load(){
    body.empty().append($('<p>').text(__('Loading finance records...')));
    try{
      const result=await frappe.call('fieldpulse.finance.overview',{request:page.fields_dict.request.get_value()||undefined});
      body.empty().append($('<p class="text-muted">').text(__('Manual payment recording. Margins use net service revenue excluding tax and recorded costs; they are provisional and are not a bank balance. Pesapal remains the source for provider transactions.')));
      for(const item of result.message.items){
        const panel=$('<section class="border rounded p-3 mb-4">').appendTo(body);
        panel.append(`<h4>${link('Diaspora Request',item.request)} · ${link('DD Task Budget',item.name)}</h4>`);
        const table=$('<table class="table table-sm">').appendTo(panel);
        for(const [key,label] of Object.entries({net_service_revenue:'Net service revenue',planned_cost:'Planned costs',planned_margin:'Planned company margin',approved_cost:'Approved costs',confirmed_service_refunds:'Confirmed service credits',margin_after_approved_costs:'Company margin after approved costs'}))table.append(`<tr><th>${esc(label)}</th><td>${esc(item.currency)} ${esc(item[key])}</td></tr>`);
        panel.append('<h5>Scout arrangements and outstanding obligations</h5>');
        for(const row of item.liabilities)panel.append(`<p>${link('DD Scout Offer',row.offer)} · ${esc(row.scout)} · ${esc(row.task||'Awaiting dispatch')}<br>${esc(row.status)} · ${esc(row.currency)} ${esc(row.net_payable)} outstanding · ${esc(row.reserved)} reserved</p>`);
        for(const [key,title,dt] of [['collections','Collections','DD Payment'],['refunds','Refund cases','DD Customer Refund'],['revisits','Revisits','DD Revisit Request'],['cases','Financial decisions','DD Finance Case']]){
          panel.append($('<h5>').text(title));
          for(const row of item[key])panel.append(`<p>${link(dt,row.name)} · ${esc(row.status)} ${esc(row.currency||'')} ${esc(row.amount||'')}</p>`);
        }
      }
      if(!result.message.items.length)body.append($('<p>').text(__('No budgets yet. Create a task budget against an issued quotation, then record scout arrangements and other planned costs.')));
    }catch(error){body.empty().append($('<p>').text(error.message||__('Finance is unavailable. Check your role and site configuration.')));}
  }
  wrapper.finance_load=load;
  wrapper.finance_page=page;
};
frappe.pages['dd-finance'].on_page_show=function(wrapper){if(frappe.route_options?.request){wrapper.finance_page.fields_dict.request.set_value(frappe.route_options.request);frappe.route_options=null;}wrapper.finance_load?.();};
