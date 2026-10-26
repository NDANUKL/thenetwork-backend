// The standard library uses streamlined templates; remove filters to inspect history.
frappe.listview_settings['FP Questionnaire'] = {
  filters: [['version', 'not in', [1, 4]], ['title', 'not like', '%University fee payment confirmation%']],
};
