frappe.listview_settings["Field Task"] = {
  hide_name_filter: true,
  hide_name_column: true,
  add_fields: ["task_number", "field_request", "scout_profile", "county", "task_brief", "status", "rework_type", "submission_review_status", "submission_review_reasons"],
  onload(listview) {
    // Desk-only choices: retain historical/internal states in the DocType and API.
    const status = listview.page.fields_dict.status;
    if (status) {
      status.df.options = "\nAssigned\nIn Progress\nSubmitted\nCorrections\nApproved\nRejected\nClosed";
      status.refresh();
    }
    const get_filters = listview.get_filters_for_args.bind(listview);
    listview.get_filters_for_args = () => get_filters().flatMap(filter => {
      if (filter[0] !== "Field Task" || filter[1] !== "status" || filter[2] !== "=") return [filter];
      if (filter[3] === "Closed") return [["Field Task", "status", "=", "Cancelled"]];
      if (filter[3] === "Corrections") return [
        ["Field Task", "status", "=", "In Progress"],
        ["Field Task", "rework_type", "=", "Correct answers"]
      ];
      // Current Task Brief rejection closes the allocation and records its outcome.
      if (filter[3] === "Rejected") return [
        ["Field Task", "status", "=", "Cancelled"],
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
    if (doc.status === "Cancelled" && doc.submission_review_status === "Reject") {
      return [__("Rejected"), "red", "status,=,Cancelled|submission_review_status,=,Reject"];
    }
    if (doc.status === "Cancelled") {
      return [__("Closed"), "gray", "status,=,Closed"];
    }
    const colors = {Assigned: "orange", Accepted: "orange", "In Progress": "blue", Submitted: "blue", Approved: "green", Cancelled: "gray"};
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
      const label = doc.status === "Cancelled" ? (closedReasons[value] || value || "Assignment closed") : (value || "Awaiting submission");
      return `<span>${escape(label)}</span>${doc.submission_review_reasons ? `<br><small title="${escape(doc.submission_review_reasons)}">${escape(doc.submission_review_reasons)}</small>` : ""}`;
    }
  }
};
