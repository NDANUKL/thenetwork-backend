const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function load(file,frappe){vm.runInNewContext(fs.readFileSync('fieldpulse/fieldpulse/doctype/'+file,'utf8'),{frappe,__:x=>x,encodeURIComponent});}
test('deactivated application exposes audited reactivation and reviewer-specific label',()=>{
 let handler,formatter,prompt,call,reloaded=false;const buttons={};
 const frappe={session:{user:'coordinator'},user_roles:['Field Operations Coordinator'],ui:{form:{on:(_,h)=>handler=h}},form:{formatters:{Link:(value,df,options,doc)=>({target:value,label:options.label||doc.full_name})}},prompt:(field,callback)=>{assert.equal(field.reqd,1);prompt=callback;},call:args=>{call=args;args.callback();}};
 load('scout_application/scout_application.js',frappe);
 const frm={doc:{name:'APP',status:'Deactivated',scout_profile:'SCOUT',full_name:'Applicant',reviewed_by:'reviewer@example.test',__onload:{reviewer_full_name:'Actual Reviewer'}},disable_save(){},is_new:()=>false,set_df_property:(name,key,value)=>{formatter=value;},refresh_field(){},remove_custom_button(){},add_custom_button:(label,fn)=>{buttons[label]=fn;return{addClass(){}};},reload_doc:()=>{reloaded=true;}};
 handler.refresh(frm);assert.ok(buttons.Reactivate);assert.ok(!buttons.Approve);
 const label=formatter(frm.doc.reviewed_by,{},null,frm.doc);assert.equal(label.label,'Actual Reviewer');assert.equal(label.target,'reviewer@example.test');
 buttons.Reactivate();prompt({reason:'Returned'});assert.equal(call.method,'fieldpulse.scout_access.reactivate_scout');assert.equal(call.args.scout_profile,'SCOUT');assert.equal(call.args.reason,'Returned');assert.equal(reloaded,true);
 delete buttons.Reactivate;frappe.user_roles=[];handler.refresh(frm);assert.ok(!buttons.Reactivate);
});
test('request subject keeps native navigation and renders number as text with title tooltip',()=>{
 const frappe={listview_settings:{}};load('field_request/field_request_list.js',frappe);
 const attrs={},link={textContent:'',setAttribute:(key,value)=>attrs[key]=value};
 const view={get_subject_element:(doc,title)=>{assert.equal(title,doc.name);return {querySelector:()=>link};}};
 const settings=frappe.listview_settings['Field Request'];settings.onload(view);
 view.get_subject_element({name:'FR-2026-00476',project_title:'River <work> "phase 2"'});
 assert.equal(link.textContent,'FR-2026-00476');assert.equal(attrs.title,'River <work> "phase 2"');assert.equal(settings.formatters.name('FR-2026-00476'),'FR-2026-00476');
});
test('submission ID is retained in schema but excluded from saved table layouts',()=>{
 const frappe={boot:{dd_native_handover_active:true},listview_settings:{}};load('diaspora_request/diaspora_request_list.js',frappe);
 const view={setup_columns(){this.columns=[{df:{fieldname:'name'}},{df:{fieldname:'submission_id'}}];},render_header(){}};
 frappe.listview_settings['Diaspora Request'].onload(view);assert.equal(view.columns.length,1);view.setup_columns();assert.equal(view.columns[0].df.fieldname,'name');
 const schema=JSON.parse(fs.readFileSync('fieldpulse/fieldpulse/doctype/diaspora_request/diaspora_request.json','utf8'));
 const field=schema.fields.find(f=>f.fieldname==='submission_id');assert.equal(field.in_list_view,0);assert.equal(field.unique,1);assert.equal(field.reqd,1);
});
test('Field Task Desk filters hide internal closure states and label ended tasks clearly',()=>{
 const frappe={listview_settings:{},utils:{escape_html:value=>String(value)}};load('field_task/field_task_list.js',frappe);
 const settings=frappe.listview_settings['Field Task'];
 const view={page:{fields_dict:{status:{df:{},refresh(){} }},add_inner_button(){}},get_filters_for_args:()=>[['Field Task','status','=','Rejected']]};
 settings.onload(view);
 assert.equal(view.page.fields_dict.status.df.options,'\nAssigned\nIn Progress\nSubmitted\nCorrections\nApproved\nRejected');
 assert.deepEqual(JSON.parse(JSON.stringify(view.get_filters_for_args())),[['Field Task','status','in',['Rejected','Cancelled']],['Field Task','submission_review_status','=','Reject']]);
 assert.equal(settings.get_indicator({status:'Rejected',submission_review_status:'Reject'})[0],'Rejected');
 assert.equal(settings.get_indicator({status:'Rejected',submission_review_status:'Rework reassigned'})[0],'Reassigned');
 assert.match(settings.formatters.submission_review_status('Rework reassigned',{}, {status:'Rejected'}),/Reassigned/);
 const schema=JSON.parse(fs.readFileSync('fieldpulse/fieldpulse/doctype/field_task/field_task.json','utf8'));
 assert.equal(schema.fields.find(field=>field.fieldname==='status').read_only,1);
 assert.ok(!schema.fields.find(field=>field.fieldname==='status').options.split('\n').includes('Cancelled'));
});
