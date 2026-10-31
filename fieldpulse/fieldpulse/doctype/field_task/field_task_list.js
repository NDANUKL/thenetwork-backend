frappe.listview_settings["Field Task"] = {
  hide_name_filter: true,
  hide_name_column: true,
  add_fields: ["task_number", "field_request", "scout_profile", "county", "task_brief", "status", "rework_type", "submission_review_status", "submission_review_reasons"],
  onload(listview) {
    // Desk choices omit server-owned terminal and transitional states.
    const status = listview.page.fields_dict.status;
    if (status) {
      status.df.options = "\nAssigned\nIn Progress\nSubmitted\nCorrections\nApproved\nRejected";
      status.refresh();
    }
    const get_filters = listview.get_filters_for_args.bind(listview);
    listview.get_filters_for_args = () => get_filters().flatMap(filter => {
      if (filter[0] !== "Field Task" || filter[1] !== "status" || filter[2] !== "=") return [filter];
      if (filter[3] === "Corrections") return [
        ["Field Task", "status", "=", "In Progress"],
        ["Field Task", "rework_type", "=", "Correct answers"]
      ];
      // Current Task Brief rejection closes the allocation and records its outcome.
      if (filter[3] === "Rejected") return [
        ["Field Task", "status", "in", ["Rejected", "Cancelled"]],
        ["Field Task", "submission_review_status", "=", "Reject"]
      ];
      return [filter];
    });
    listview.page.add_inner_button(__("County assignment balance"), () => frappe.set_route("query-report", "County Assignment Balance"));
  },
  get_indicator(doc) {
    if (doc.status === "In Progress" && doc.rework_type === "Correct answers") {
      return [__("Corrections"), "orange", "status,=,In Progress|rework_type,=,Correct answers"];
    }
    if ((doc.status === "Rejected" || doc.status === "Cancelled") && doc.submission_review_status === "Reject") {
      return [__("Rejected"), "red", `status,=,${doc.status}|submission_review_status,=,Reject`];
    }
    if (doc.status === "Rejected" || doc.status === "Cancelled") {
      const label = doc.submission_review_status === "Request additional evidence" ? __("Additional evidence requested") : doc.submission_review_status === "Returned for reassignment" ? __("Returned for reassignment") : doc.submission_review_status === "Rework reassigned" ? __("Reassigned") : __("Ended");
      return [label, "gray", `status,=,${doc.status}`];
    }
    const colors = {Assigned: "orange", Accepted: "orange", "In Progress": "blue", Submitted: "blue", Approved: "green"};
    return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
  },
  formatters: {
    field_request(value, df, doc) {
      const escape = frappe.utils.escape_html;
      return `<a href="/app/field-request/${encodeURIComponent(value || '')}" title="${escape(doc.task_brief || __('No brief recorded'))}">${escape(value || '')}</a>`;
    },
    submission_review_status(value, df, doc) {
      const escape = frappe.utils.escape_html;
      const closedReasons = {Reject: "Rejected", "Request additional evidence": "Returned for reassignment", "Returned for reassignment": "Returned for reassignment", "Rework reassigned": "Reassigned"};
      const ended = ["Cancelled", "Rejected"].includes(doc.status);
      const label = ended ? (closedReasons[value] || value || "Assignment ended") : (value || "Awaiting submission");
      return `<span>${escape(label)}</span>${doc.submission_review_reasons ? `<br><small title="${escape(doc.submission_review_reasons)}">${escape(doc.submission_review_reasons)}</small>` : ""}`;
    }
  }
};
