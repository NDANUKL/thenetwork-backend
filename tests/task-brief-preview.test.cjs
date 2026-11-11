const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let handlers;
const context = {frappe:{ui:{form:{on(_doctype, value){handlers = value;}}}}, __: value => value};
vm.createContext(context);
vm.runInContext(fs.readFileSync('fieldpulse/fieldpulse/doctype/dd_task_brief/dd_task_brief.js','utf8'), context);
const fixture = JSON.parse(fs.readFileSync('tests/fixtures/task-brief-v1.json','utf8')).brief;

function form(status, content) {
  const result = {html:'', buttons:[], hidden:false, disabled:false};
  const frm = {doc:{status, content_json:content}, fields_dict:{brief_preview:{$wrapper:{html(value){result.html=value;}}}},
    set_df_property(field, property, value){if(field==='content_json' && property==='hidden')result.hidden=value;},
    is_new:()=>false, add_custom_button(label){result.buttons.push(label);}, disable_save(){result.disabled=true;}};
  handlers.refresh(frm);
  return {result, frm};
}

test('draft and approved forms show checklist and preserve editing rules', () => {
  for (const status of ['Draft', 'Approved']) {
    const {result} = form(status, JSON.stringify(fixture));
    assert.equal(result.hidden, 1);
    assert.match(result.html, /Objective/);
    assert.match(result.html, /Field checks/);
    assert.ok(result.html.includes(fixture.checks[0].instruction));
    assert.doesNotMatch(result.html, /schema_version|content_json/);
    assert.equal(result.buttons.includes('Edit Task Brief'), status==='Draft');
    assert.equal(result.disabled, status==='Approved');
  }
});

test('untrusted brief text is escaped including choices, review reasons and capture instructions', () => {
  const unsafe = '<img src=x onerror=alert(1)>';
  const brief = {...fixture, objective:unsafe, scope:unsafe, deliverables:[unsafe], instructions:[unsafe],
    review_required:true, review_reasons:[unsafe], checks:[{instruction:unsafe, required:true,
      response_type:'single', options:[unsafe], evidence:[{kind:'photo',minimum:2,instruction:unsafe}]}]};
  const {result} = form('Draft', JSON.stringify(brief));
  assert.doesNotMatch(result.html, /<img|<script/);
  assert.match(result.html, /&lt;img/);
  assert.match(result.html, /Photos/);
  assert.match(result.html, /Minimum/);
  assert.match(result.html, /Choose one option/);
});

test('empty and malformed briefs explain the state and content changes refresh the preview', () => {
  const {result, frm} = form('Draft', JSON.stringify({...fixture, checks:[],review_required:false,review_reasons:['Clarify site access']}));
  assert.match(result.html, /No field checks/);
  assert.match(result.html, /Clarify site access/);
  frm.doc.content_json = '{malformed';
  handlers.content_json(frm);
  assert.match(result.html, /could not be displayed/);
  assert.doesNotMatch(result.html, /malformed/);
  frm.doc.content_json = JSON.stringify(fixture);
  handlers.content_json(frm);
  assert.ok(result.html.includes(fixture.checks[0].instruction));
});

test('schema hides storage and supplies an HTML preview without changing its field type', () => {
  const schema = JSON.parse(fs.readFileSync('fieldpulse/fieldpulse/doctype/dd_task_brief/dd_task_brief.json','utf8'));
  assert.equal(schema.fields.find(field=>field.fieldname==='content_json').hidden,1);
  assert.equal(schema.fields.find(field=>field.fieldname==='content_json').fieldtype,'Code');
  assert.equal(schema.fields.find(field=>field.fieldname==='brief_preview').fieldtype,'HTML');
});


test('missing preview metadata gives an actionable warning rather than a blank form', () => {
  let intro;
  context.renderTaskBrief({doc:{content_json:JSON.stringify(fixture)},fields_dict:{},
    set_df_property(){},set_intro(value){intro=value;}});
  assert.match(intro,/schema update/);
});

test('structured editor saves check identities and refreshes the readable preview', async () => {
  let dialog; let saved=0; let hidden=false;
  const frm={doc:{status:'Draft',content_json:JSON.stringify(fixture)},
    fields_dict:{brief_preview:{$wrapper:{html(value){hidden=value.includes('Field checks');}}}},
    set_df_property(){},async set_value(key,value){this.doc[key]=value;handlers.content_json(this);},async save(){saved++;}};
  context.frappe.utils={to_title_case:value=>value};
  context.frappe.ui.Dialog=class {constructor(options){dialog=options;}show(){}hide(){}};
  context.editTaskBrief(frm);
  const checks=dialog.fields.find(field=>field.fieldname==='checks').data;
  await dialog.primary_action({title:fixture.title,category:fixture.category,objective:fixture.objective,
    scope:fixture.scope,deliverables:fixture.deliverables.join('\n'),instructions:fixture.instructions.join('\n'),checks});
  const stored=JSON.parse(frm.doc.content_json);
  assert.deepEqual(stored.checks,fixture.checks);
  assert.equal(saved,1);
  assert.equal(hidden,true);
});
