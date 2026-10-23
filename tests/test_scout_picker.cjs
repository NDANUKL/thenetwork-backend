const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
let assign;
let dialog;
const frappe = {
  boot: { dd_native_handover_active: true },
  ui: { form: { on: (_name, handlers) => { if (handlers.refresh?.toString().includes('Assign scouts')) assign = handlers.refresh; } },
    Dialog: function(options) { Object.assign(this, options); this.fields_dict = {assignments: {grid: {refresh() {}}}}; this.show = () => {}; dialog = this; } },
  db: {get_value: async () => ({message: {scout_name: 'Pauline Wanjiku', base_county: 'Nairobi'}})},
};
vm.runInNewContext(fs.readFileSync('fieldpulse/fieldpulse/doctype/field_request/field_request.js', 'utf8'), {frappe, __: x => x});
const frm = {doc: {name: 'FR-1', project_number: 1, county: 'Nairobi'}, perm: [{write: 1}], is_new: () => false,
  is_dirty: () => false, remove_custom_button() {}, set_df_property() {}, add_custom_button(_label, callback) { callback(); }};
assign(frm);
const fields = dialog.fields.find(f => f.fieldname === 'assignments').fields;
const scout = fields.find(f => f.fieldname === 'scout');
(async () => {
  const row = {scout: 'SCT-1'};
  await scout.onchange.call({doc: row});
  assert.equal(row.scout_name, 'Pauline Wanjiku');
  assert.equal(row.base_county, 'Nairobi');
  row.scout = '';
  await scout.onchange.call({doc: row});
  assert.equal(row.base_county, '');
  let resolve;
  frappe.db.get_value = () => new Promise(done => {resolve = done;});
  row.scout = 'SCT-1';
  const pending = scout.onchange.call({doc: row});
  row.scout = 'SCT-2';
  resolve({message: {scout_name: 'Old scout', base_county: 'Old county'}});
  await pending;
  assert.equal(row.scout_name, '');
  console.log('Assignment picker: identity, county, clearing and stale responses pass.');
})().catch(error => {console.error(error); process.exitCode = 1;});
