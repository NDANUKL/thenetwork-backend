const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function buttonsFor(doc) {
  const handlers = [], buttons = new Map([['Prepare quotation', () => {}]]);
  const frappe = {
    boot: {dd_native_handover_active: true},
    ui: {form: {on: (doctype, events) => handlers.push(events)}},
  };
  vm.runInNewContext(fs.readFileSync('fieldpulse/fieldpulse/doctype/diaspora_request/diaspora_request.js', 'utf8'), {
    frappe, __: text => text,
  });
  // The quotation actions are registered separately from location and details actions.
  handlers[1].refresh({
    doc, is_new: () => false, perm: [{write: 1}],
    add_custom_button: (label, action) => buttons.set(label, action),
    remove_custom_button: label => buttons.delete(label),
  });
  return buttons;
}

test('out-of-scope requests remove quotation creation and retain history', () => {
  for (const doc of [
    {assessment_status: 'out_of_scope'},
    {category: 'out_of_scope'},
    {assessment_status: 'supported', category: 'out_of_scope'},
  ]) {
    const buttons = buttonsFor(doc);
    assert.equal(buttons.has('Prepare quotation'), false);
    assert.equal(buttons.has('Quotations'), true);
  }
});

test('supported and legacy requests retain quotation creation', () => {
  for (const doc of [{assessment_status: 'supported'}, {category: 'land_property_check'}]) {
    assert.equal(buttonsFor(doc).has('Prepare quotation'), true);
  }
});
