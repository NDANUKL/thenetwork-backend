frappe.listview_settings["DD Customer Account"] = {
  add_fields: ["beta_access", "email_verified", "account_access"],
  get_indicator(doc) {
    if (doc.account_access === "Deactivated") return [__("Deactivated"), "grey", "account_access,=,Deactivated"];
    const status = doc.beta_access || "Approved";
    return [__(status), {Pending: "orange", Approved: "green", Rejected: "red"}[status], "beta_access,=," + (doc.beta_access || "")];
  }
};
