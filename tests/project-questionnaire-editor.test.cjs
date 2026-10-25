const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../fieldpulse/fieldpulse/doctype/field_request/field_request.js'),'utf8');
(async()=>{
 const handlers={},dialogs=[],calls=[],values={},row={name:'new-row',doctype:'DD Scout Check',question:null,label:'What proportion of maize appears harvested?',answer_format:'Template format'};
 const frm={doc:{name:'project',scout_checks:[row],modified:'revision-1'},is_new:()=>false,is_dirty:()=>true,save:async()=>{frm.doc.modified='revision-2';},reload_doc:async()=>{},refresh_field(){},set_df_property(){},add_custom_button:(label,fn)=>{handlers[label]=fn;},set_value:async(k,v)=>{values[k]=v;}};
 const registrations={};
 const frappe={boot:{dd_native_handover_active:false},user:{has_role:()=>true},ui:{form:{on:(name,definition)=>{(registrations[name]??=[]).push(definition);}},Dialog:class{constructor(options){this.options=options;dialogs.push(this);}set_values(v){this.values=v;}show(){}hide(){}}},
  call:async(method,args)=>{calls.push({method,args});return {message:{confirmed:true}};},model:{set_value:async(cdt,cdn,key,value)=>{row[key]=value;}},show_alert(){},msgprint(){},utils:{escape_html:v=>String(v)}};
 vm.runInNewContext(source,{frappe,__:v=>v,locals:{'DD Scout Check':{'new-row':row}}});
 const editor=registrations['DD Scout Check'].find(h=>h.edit_question);
 await editor.edit_question(frm,'DD Scout Check','new-row');
 const dialog=dialogs[0];
 assert.equal(dialog.values.answer_format,'Written answer');
 assert.equal(dialog.values.evidence_mode,'Specify evidence');
 await dialog.options.primary_action({label:'What proportion of maize appears harvested?',instructions:'Describe visible crop conditions.',answer_format:'Single choice',answer_options:'Standing\nPartly harvested\nFully harvested',evidence_mode:'Specify evidence',evidence:[{kind:'Photo',subject:'Maize crop and harvested rows'}]});
 assert.equal(row.answer_format,'Single choice');assert.equal(JSON.parse(row.evidence_json)[0].subject,'Maize crop and harvested rows');
 assert.equal(values.scout_checks_confirmed,0);
 assert.equal(calls.length,0,'A new project question must not mutate a shared template through an API.');
 registrations['Field Request'].at(-1).refresh(frm);
 await handlers['Confirm questionnaire']();
 assert.equal(calls.at(-1).method,'fieldpulse.scout_v2.confirm_project_questionnaire');
 assert.equal(calls.at(-1).args.expected_modified,'revision-2');
 assert.ok(!handlers['Map customer questions']);
 console.log('PASS: project question editor, maize choices/evidence, confirmation invalidation and saved-version review');
})().catch(error=>{console.error(error);process.exitCode=1;});
