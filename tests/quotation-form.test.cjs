const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
function setup() {
 const handlers = {}, notices = [], locals = {'DD Quotation Item': {}};
 const frappe = {boot:{dd_native_handover_active:true}, ui:{form:{on:(dt,h)=>Object.assign(handlers[dt] ||= {},h)}},
  model:{set_value:async(dt,n,key,value)=>Object.assign(locals[dt][n],typeof key==='object'?key:{[key]:value})},
  db:{get_value:async()=>({message:{deadline:'2026-11-10'}})},msgprint:m=>notices.push(m),throw:m=>{throw Error(m);}};
 vm.runInNewContext(fs.readFileSync('fieldpulse/fieldpulse/doctype/dd_quotation/dd_quotation.js','utf8'),{frappe,locals});
 const rows = ['a','b'].map((name,i)=>locals['DD Quotation Item'][name]={name,doctype:'DD Quotation Item',field_request:'project-'+i});
 const frm = {doc:{items:rows,request:'request',status:'Draft',pricing_mode:'Live - USD 100 per project',currency:'USD',discount_value:10,discount_type:'Fixed amount'},
  is_new:()=>false,set_query:(_f,_t,q)=>{frm.query=q;},set_value:async(k,v)=>Object.assign(frm.doc,typeof k==='object'?k:{[k]:v}),refresh_field(){},set_df_property(){},dirty(){}};
 return {frm,rows,notices,parent:handlers['DD Quotation'],child:handlers['DD Quotation Item']};
}
test('picker excludes selected projects and duplicate entry is cleared',async()=>{
 const {frm,rows,notices,parent,child}=setup();parent.setup(frm);
 assert.deepEqual(JSON.parse(JSON.stringify(frm.query(null,null,'b').filters)),{diaspora_request:'request',name:['not in',['project-0']]});
 rows[1].field_request=rows[0].field_request;
 assert.throws(()=>parent.validate(frm),/only once/);
 await child.field_request(frm,'DD Quotation Item','b');
 assert.equal(rows[1].field_request,null);assert.equal(notices.length,1);
});
test('pricing switches all draft rows and clears old currency discount',async()=>{
 const {frm,rows,parent}=setup();frm.doc.pricing_mode='Beta - KSh 1 per project';
 await parent.pricing_mode(frm);
 assert.equal(frm.doc.currency,'KES');assert.equal(frm.doc.discount_value,0);assert.equal(frm.doc.tax_inclusive,1);
 assert.ok(rows.every(row=>row.rate===1&&row.amount===1));assert.equal(frm.doc.total,2);assert.equal(frm.doc.deposit_amount,1);
 frm.doc.pricing_mode='Live - USD 100 per project';await parent.pricing_mode(frm);
 assert.equal(frm.doc.currency,'USD');assert.ok(rows.every(row=>row.rate===100));assert.equal(frm.doc.total,232);
 frm.doc.status='Issued';frm.doc.pricing_mode='Beta - KSh 1 per project';await parent.pricing_mode(frm);
 assert.equal(frm.doc.currency,'USD');assert.ok(rows.every(row=>row.rate===100));assert.equal(frm.doc.total,232);
});
test('row currency formatting follows quotation currency',()=>{
 const meta=JSON.parse(fs.readFileSync('fieldpulse/fieldpulse/doctype/dd_quotation_item/dd_quotation_item.json','utf8'));
 for(const name of ['rate','amount'])assert.equal(meta.fields.find(f=>f.fieldname===name).options,'currency');
});
