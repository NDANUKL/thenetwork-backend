const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function screen(doctype, doc, roles, dirty = false) {
  let refresh, prompt, call, message;
  const buttons = {};
  const frappe = {
    session: {user: 'staff@example.test'}, user_roles: roles,
    user: {has_role: role => roles.includes(role)},
    ui: {form: {on: (_doctype, handlers) => {refresh = handlers.refresh;}}},
    prompt: (fields, submit) => {prompt = {fields, submit};},
    call: options => {call = options;},
    msgprint: value => {message = value;},
  };
  const name = doctype.toLowerCase().replaceAll(' ', '_');
  vm.runInNewContext(fs.readFileSync(`fieldpulse/fieldpulse/doctype/${name}/${name}.js`, 'utf8'), {frappe, __: text => text});
  const frm = {
    doc, is_new: () => false, is_dirty: () => dirty, fields: [],
    add_custom_button: (label, callback) => {buttons[label] = callback; return {addClass() {}};},
    remove_custom_button: label => {delete buttons[label];},
    set_intro() {}, set_df_property() {}, disable_save() {}, reload_doc() {},
  };
  refresh(frm);
  return {buttons, prompt: () => prompt, call: () => call, message: () => message};
}

const client = {name: 'CLIENT-1', user: 'client@example.test', beta_access: 'Approved', account_access: 'Active'};
let view = screen('DD Customer Account', client, ['System Manager']);
assert.deepEqual(Object.keys(view.buttons), ['Deactivate']);
view = screen('DD Customer Account', {...client, beta_access: ''}, ['System Manager']);
assert.deepEqual(Object.keys(view.buttons), ['Deactivate']);
view = screen('DD Customer Account', {...client, beta_access: 'Pending'}, ['System Manager']);
assert.deepEqual(Object.keys(view.buttons).sort(), ['Approve', 'Reject']);
view = screen('DD Customer Account', {...client, beta_access: 'Rejected'}, ['System Manager']);
assert.deepEqual(Object.keys(view.buttons), ['Approve']);
view = screen('DD Customer Account', {...client, account_access: 'Deactivated', beta_access: 'Pending'}, ['System Manager']);
assert.deepEqual(Object.keys(view.buttons), ['Reactivate']);
view.buttons.Reactivate();
assert.equal(view.prompt().fields.reqd, 1);
view.prompt().submit({reason: 'Client returned'});
assert.equal(view.call().method, 'fieldpulse.customer_access.set_account_access');
assert.equal(view.call().args.action, 'Reactivate');
assert.equal(view.call().args.account, 'CLIENT-1');
assert.equal(view.call().args.reason, 'Client returned');
view = screen('DD Customer Account', client, ['Field Operations Coordinator']);
assert.deepEqual(Object.keys(view.buttons), []);
view = screen('DD Customer Account', client, ['System Manager'], true);
view.buttons.Deactivate();
assert.equal(view.prompt(), undefined);
assert.match(view.message(), /Save or discard/);

const scout = {name: 'SCT-1', user: 'scout@example.test', access_status: 'Deactivated'};
view = screen('Scout Profile', scout, ['Field Operations Coordinator']);
assert.deepEqual(Object.keys(view.buttons), ['Reactivate']);
view.buttons.Reactivate();
view.prompt().submit({reason: 'Scout returned'});
assert.equal(view.call().method, 'fieldpulse.scout_access.reactivate_scout');
assert.equal(view.call().args.scout_profile, 'SCT-1');
view = screen('Scout Profile', {...scout, access_status: 'Active'}, ['Field Operations Coordinator']);
assert.deepEqual(Object.keys(view.buttons), ['Deactivate']);
for (const status of ['Pending', 'Rejected']) {
  view = screen('Scout Profile', {...scout, access_status: 'Active', __onload: {scout_application_status: status}}, ['Field Operations Coordinator']);
  assert.deepEqual(Object.keys(view.buttons), []);
}
view = screen('Scout Profile', scout, ['Field Agent']);
assert.deepEqual(Object.keys(view.buttons), []);
for (const status of ['Approved', 'Rejected', 'Deactivated']) {
  view = screen('Scout Application', {name: 'SAPP-1', status}, ['Field Operations Coordinator']);
  assert.deepEqual(Object.keys(view.buttons), []);
}
view = screen('Scout Application', {name: 'SAPP-1', status: 'Pending'}, ['Field Operations Coordinator']);
assert.deepEqual(Object.keys(view.buttons).sort(), ['Approve', 'Reject']);
console.log('PASS: approval-state-specific client/scout controls, no Remove access, required reason, endpoint routing and unsaved-edit protection');
