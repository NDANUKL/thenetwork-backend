frappe.query_reports["County Assignment Balance"] = {
  filters: [
    {fieldname: "from_date", label: __("Assigned from"), fieldtype: "Date"},
    {fieldname: "to_date", label: __("Assigned to"), fieldtype: "Date"},
    {fieldname: "field_request", label: __("Field Request"), fieldtype: "Link", options: "Field Request"},
    {fieldname: "county", label: __("Project County"), fieldtype: "Data"},
    {fieldname: "scout_county", label: __("Scout County"), fieldtype: "Data"}
  ]
};
