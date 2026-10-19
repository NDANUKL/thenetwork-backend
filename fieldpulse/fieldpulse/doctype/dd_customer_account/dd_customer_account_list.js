frappe.listview_settings["DD Customer Account"] = {
  add_fields: ["beta_access", "email_verified"],
  get_indicator(doc) {
    const status = doc.beta_access || "Approved";
    return [__(status), {Pending: "orange", Approved: "green", Rejected: "red"}[status], "beta_access,=," + (doc.beta_access || "")];
  }
};
