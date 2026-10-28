const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const handlers=[];
const frappe={boot:{dd_native_handover_active:true},ui:{form:{on:(_name,h)=>handlers.push(h)}}};
vm.runInNewContext(fs.readFileSync('fieldpulse/fieldpulse/doctype/field_request/field_request.js','utf8'),{frappe,__:x=>x});
test('empty legacy evidence field does not warn on approved Task Brief',()=>{
 let intro;
 const frm={doc:{diaspora_request:'REQUEST',county:'Kisumu',approved_task_brief:'BRIEF',evidence_requirements:''},set_df_property(){},set_intro:value=>intro=value};
 handlers[0].refresh(frm);assert.equal(intro,'');
 frm.doc.approved_task_brief=null;handlers[0].refresh(frm);
 assert.match(intro,/Review and approve/);assert.doesNotMatch(intro,/evidence requirements/);
});
test('open action routes to project-specific existing brief',async()=>{
 let open;let route;
 frappe.call=async args=>{assert.equal(args.args.project,'PROJECT');return {message:'GENERATED'};};
 frappe.set_route=(...args)=>route=args;
 handlers[2].refresh({doc:{name:'PROJECT'},is_new:()=>false,is_dirty:()=>false,set_query(){},add_custom_button(label,fn){if(label==='Open Task Brief')open=fn;}});
 await open();assert.deepEqual(route,['Form','DD Task Brief','GENERATED']);
});
