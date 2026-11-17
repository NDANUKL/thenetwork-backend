const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup(value, isNew = true) {
  const handlers = {};
  const frappe = {
    ui: { form: { on: (doctype, events) => { handlers[doctype] = events; } } },
    datetime: { get_today: () => '2026-11-17' },
    throw: message => { throw new Error(message); },
  };
  vm.runInNewContext(fs.readFileSync('fieldpulse/public/js/planning_dates.js', 'utf8'), {
    frappe, __: (message, args) => args ? message.replace('{0}', args[0]) : message,
  });
  const control = { df: { label: 'Valid until', read_only: 0 } };
  // A calendar access or input handler would interfere with native selection.
  for (const name of ['datepicker', '$input', '$wrapper']) {
    Object.defineProperty(control, name, { get() { throw new Error(`Calendar touched: ${name}`); } });
  }
  const frm = { doc: { valid_until: value }, fields_dict: { valid_until: control }, is_new: () => isNew };
  return { events: handlers['DD Quotation'], frm };
}

test('quotation date lifecycle leaves the native calendar untouched', () => {
  const { events, frm } = setup('2026-11-17');
  assert.deepEqual(Object.keys(events).sort(), ['onload', 'validate']);
  events.onload(frm);
  events.validate(frm);
});

test('new quotation save rejects yesterday and accepts today or a future date', () => {
  for (const value of ['2026-11-16', '2026-11-17', '2026-12-01']) {
    const { events, frm } = setup(value);
    events.onload(frm);
    if (value < '2026-11-17') assert.throws(() => events.validate(frm), /Valid until must be today or later/);
    else assert.doesNotThrow(() => events.validate(frm));
  }
});

test('changing an existing quotation date cannot backdate it', () => {
  const { events, frm } = setup('2026-11-15', false);
  events.onload(frm);
  assert.doesNotThrow(() => events.validate(frm));
  frm.doc.valid_until = '2026-11-16';
  assert.throws(() => events.validate(frm), /today or later/);
  frm.doc.valid_until = '2026-11-17';
  assert.doesNotThrow(() => events.validate(frm));
});
