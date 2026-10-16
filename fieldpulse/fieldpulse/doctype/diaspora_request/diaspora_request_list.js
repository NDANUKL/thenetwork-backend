if (frappe.boot.dd_native_handover_active) {
// DD Submission List
frappe.listview_settings["Diaspora Request"] = { ...frappe.listview_settings["Diaspora Request"], get_indicator: () => null };

}
