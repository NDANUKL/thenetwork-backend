frappe.listview_settings["FP Task Response"] = {
  add_fields: ["status", "task", "rework_of", "review_status", "review_reasons", "qa_status", "reviewed_by"],
  get_indicator(doc) {
    if (doc.status === "Draft" && doc.rework_of) {
      return [__("Rework in progress"), "orange", "status,=,Draft|rework_of,is,set"];
    }
    if (doc.qa_status === "Passed") return [__("Reviewed"), "green", "qa_status,=,Passed"];
    if (doc.qa_status === "Failed") return [__("Rework requested"), "red", "qa_status,=,Failed"];
    if (doc.status === "Submitted") {
      return [__(doc.review_status || "Pending review"), doc.review_status === "Needs review" ? "orange" : "blue", "status,=,Submitted"];
    }
    return [__(doc.status || "Unknown"), "gray", `status,=,${doc.status || ""}`];
  }
};
