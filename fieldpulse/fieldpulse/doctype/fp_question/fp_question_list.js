// Hide superseded shared templates from the standard library.
// Remove the filter to inspect historical questions.
frappe.listview_settings['FP Question'] = {
  filters: [['questionnaire', 'not in', [
    "DD-land-v1",
    "DD-property-v1",
    "DD-construction-v1",
    "DD-business-v1",
    "DD-vehicle-v1",
    "DD-equipment-v1",
    "DD-adult_enrolment-v1",
    "DD-university_fees-v1",
    "DD-adult_attendance-v1",
    "DD-adult_clinic-v1",
    "DD-document-v1",
    "DD-receipt-v1",
    "DD-delivery-v1",
    "DD-general_visit-v1",
    "DD-merchant_survey-v1",
    "DD-university_fees-v2",
    "DD-university_fees-v3",
    "DD-university_fees-v4"
]]],
};
