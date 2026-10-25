const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../fieldpulse/fieldpulse/doctype/fp_task_response/fp_task_response.js'), 'utf8');
(async () => {
  let refresh, fields, submit, sent, route;
  const buttons = {};
  const wrapper = {html: () => wrapper, find: () => ({on() {}})};
  const frappe = {
    ui: {form: {on: (_, definition) => {refresh = definition.refresh;}}}, user: {has_role: () => true}, utils: {escape_html: value => String(value)},
    call: async (method, values) => {
      if (method.endsWith('review_submission')) {sent = values; return {message: {revisit_request: values.rework_type === 'Return to site' ? 'revisit' : null}};}
      return {message: {questions: [{name: 'q', question_code: '1.1', label: 'Boundary'}], answers: [], evidence: []}};
    },
    prompt: (items, callback) => {fields = items; submit = callback;}, msgprint() {}, show_alert() {}, set_route: (...args) => {route = args;}
  };
  vm.runInNewContext(source, {frappe, __: text => text});
  await refresh({is_new: () => false, doc: {name: 'response', agent: 'original', status: 'Submitted'}, fields_dict: {submission_review: {$wrapper: wrapper}},
    add_custom_button: (label, callback) => {buttons[label] = callback;}, reload_doc: async () => {}});
  buttons['Request rework']();
  assert.equal(fields.find(f => f.fieldname === 'rework_assignment').default, 'Same scout');
  const scout = fields.find(f => f.fieldname === 'replacement_scout');
  assert.match(scout.mandatory_depends_on, /Return to site/);
  assert.equal(scout.get_query().filters.name[1], 'original');
  assert.match(fields.find(f => f.fieldname === 'reassignment_reason').mandatory_depends_on, /Assign another scout/);
  await submit({notes: 'Clarify', rework_type: 'Correct answers', rework_assignment: 'Assign another scout', replacement_scout: 'new', reassignment_reason: 'Stale hidden field', rework_questions: ['1.1']});
  assert.equal(sent.rework_assignment, 'Same scout');
  assert.equal(sent.replacement_scout, null);
  await submit({notes: 'Verify site', rework_type: 'Return to site', rework_assignment: 'Assign another scout', replacement_scout: 'new', reassignment_reason: 'Unavailable', rework_questions: ['1.1']});
  assert.equal(sent.replacement_scout, 'new');
  assert.equal(sent.reassignment_reason, 'Unavailable');
  assert.deepEqual(route, ['Form', 'DD Revisit Request', 'revisit']);
  console.log('PASS: same-scout default, conditional reassignment fields, hidden-field isolation and new-task navigation');
})().catch(error => {console.error(error); process.exitCode = 1;});
