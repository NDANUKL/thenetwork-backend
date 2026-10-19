frappe.listview_settings["FP Task Response"] = {
  add_fields: ["review_status", "review_reasons", "qa_status"],
  get_indicator(doc) {
    if (doc.qa_status === "Passed") return [__("Reviewed"), "green", "qa_status,=,Passed"];
    if (doc.qa_status === "Failed") return [__("Rework requested"), "red", "qa_status,=,Failed"];
    return [__(doc.review_status || "Pending review"), doc.review_status === "Needs review" ? "orange" : "blue", "status,=,Submitted"];
  }
};
