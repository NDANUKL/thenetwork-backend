// Keep historical questions for pinned assignments, but omit the superseded
// university fee templates from the default question library. Remove this
// filter when inspecting historical questionnaires.
frappe.listview_settings['FP Question'] = {
  filters: [['questionnaire', 'not in', [
    'DD-university_fees-v1',
    'DD-university_fees-v2',
    'DD-university_fees-v3',
  ]]],
};
