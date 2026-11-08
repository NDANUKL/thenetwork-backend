const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('fieldpulse/fieldpulse/doctype/fp_task_response/fp_task_response.js', 'utf8');
const reportSource = fs.readFileSync('fieldpulse/fieldpulse/doctype/dd_service_report/dd_service_report.js', 'utf8');

function reportForm(status = 'Draft', failure = false) {
  let handlers;
  const buttons = new Map(), calls = [], opened = [], hidden = [], events = new Map();
  const tab = {location: {replace: url => opened.push(url)}, close: () => calls.push('close')};
  const frappe = {
    ui: {form: {on: (doctype, value) => {if (doctype === 'DD Service Report') handlers = value;}}},
    call: async options => {
      calls.push(options.method);
      if (failure) throw new Error('Review evidence first');
      return {message: {file: '/private/files/client-report.pdf'}};
    },
  };
  vm.runInNewContext(reportSource, {frappe, __: value => value,
    $: () => ({on: (name, handler) => events.set(name, handler)}),
    window: {open: () => tab}});
  const frm = {events: handlers, doc: {name: 'report', status}, wrapper: {},
    is_new: () => false, is_dirty: () => status !== 'Approved',
    save: async () => calls.push('save'), reload_doc: async () => calls.push('reload'),
    toolbar: {print_icon: {hide: () => hidden.push('print')}},
    page: {menu: {find: () => ({filter: () => ({closest: () => ({remove: () => hidden.push('Print')})})})}},
    attachments: {parent: {hide: () => hidden.push('attachments')}}, set_intro() {},
    add_custom_button: (label, handler) => buttons.set(label, handler)};
  handlers.setup(frm);
  handlers.refresh(frm);
  return {frm, buttons, calls, opened, hidden, events, tab};
}

test('one PDF preview saves edits, prepares the PDF and opens it', async () => {
  const view = reportForm();
  assert.ok(view.buttons.has('Preview report PDF'));
  assert.ok(!view.buttons.has('Generate report PDF'));
  assert.deepEqual(view.hidden, ['print', 'Print', 'attachments']);
  await view.buttons.get('Preview report PDF')();
  assert.deepEqual(view.calls, ['save', 'fieldpulse.scout_reports.preview_pdf', 'reload']);
  assert.deepEqual(view.opened, ['/private/files/client-report.pdf']);
  assert.equal(view.tab.opener, null);
  view.events.get('attachments_change.dd_service_report')();
  assert.equal(view.hidden.at(-1), 'attachments');
});

test('approved reports and keyboard printing use the same PDF preview', async () => {
  const view = reportForm('Approved');
  assert.deepEqual([...view.buttons.keys()], ['Preview report PDF']);
  await view.frm.print_doc();
  assert.deepEqual(view.calls, ['fieldpulse.scout_reports.preview_pdf', 'reload']);
  assert.deepEqual(view.opened, ['/private/files/client-report.pdf']);
});

test('failed preview closes its blank tab and does not reload', async () => {
  const view = reportForm('Draft', true);
  await assert.rejects(view.buttons.get('Preview report PDF')(), /Review evidence first/);
  assert.deepEqual(view.calls, ['save', 'fieldpulse.scout_reports.preview_pdf', 'close']);
  assert.deepEqual(view.opened, []);
});

test('approved response exposes draft navigation without requiring a pre-existing report', async () => {
  let refresh;
  const calls = [], buttons = new Map(), routes = [];
  const wrapper = {html() {}, find: () => ({on() {}})};
  const data = {brief: {brief: {title: 'Site visit', checks: []}, check_ids: []}, submission: {}};
  const frappe = {
    ui: {form: {on: (_name, handlers) => {refresh = handlers.refresh;}}},
    user: {has_role: () => true}, utils: {escape_html: value => String(value)},
    call: async (method, args) => {
      calls.push([method, args]);
      return {message: typeof method === 'string' ? data : {report: 'draft'}};
    },
    set_route: (...args) => routes.push(args),
  };
  vm.runInNewContext(source, {frappe, __: value => value});
  await refresh({is_new: () => false, doc: {name: 'response', status: 'Submitted', qa_status: 'Passed'},
    fields_dict: {submission_review: {$wrapper: wrapper}}, add_custom_button: (label, handler) => buttons.set(label, handler)});
  assert.ok(buttons.has('View draft report'));
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'fieldpulse.scout_submissions.submission_detail');
  await buttons.get('View draft report')();
  assert.equal(calls[1][0].method, 'fieldpulse.scout_reports.open_draft_for_response');
  assert.equal(calls[1][0].args.response, 'response');
  assert.deepEqual(routes, [['Form', 'DD Service Report', 'draft']]);
});
