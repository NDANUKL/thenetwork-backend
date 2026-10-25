// Old publications remain available to pinned visits and through explicit history filters.
// New work uses the single School fee payment confirmation service (all institutions).
frappe.listview_settings['FP Questionnaire'] = {
  filters: [['title', 'not like', '%University fee payment confirmation%']],
};
