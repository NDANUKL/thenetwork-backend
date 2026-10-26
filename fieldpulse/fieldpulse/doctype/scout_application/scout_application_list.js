frappe.listview_settings["Scout Application"] = {
  add_fields: ["status"],
  get_indicator(doc) {
    return [__(doc.status), { Pending: "orange", Approved: "green", Rejected: "red", Deactivated: "grey" }[doc.status], `status,=,${doc.status}`];
  },
};
