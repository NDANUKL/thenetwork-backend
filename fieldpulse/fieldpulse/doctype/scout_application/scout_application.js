frappe.ui.form.on("Scout Application", {
  refresh(frm) {
    frm.disable_save();
    frm.set_df_property("reviewed_by", "formatter", (value, df, options, doc) =>
      frappe.form.formatters.Link(value, df,
        { ...options, label: doc?.__onload?.reviewer_full_name || value }, doc));
    frm.refresh_field("reviewed_by");
    frm.remove_custom_button(__("Reactivate"));
    if (frm.is_new()) return;
    const reviewer = frappe.session.user === "Administrator" ||
      ["System Manager", "Admin", "Field Operations Coordinator"].some(role => frappe.user_roles.includes(role));
    if (!reviewer) return;
    if (frm.doc.status === "Deactivated" && frm.doc.scout_profile) {
      frm.add_custom_button(__("Reactivate"), () => frappe.prompt(
        { fieldname: "reason", fieldtype: "Small Text", label: __("Reason for reactivation"), reqd: 1 },
        values => frappe.call({
          method: "fieldpulse.scout_access.reactivate_scout",
          args: { scout_profile: frm.doc.scout_profile, reason: values.reason },
          freeze: true, callback: () => frm.reload_doc(),
        }), __("Reactivate scout access"), __("Reactivate")
      ));
    }
    if (frm.doc.status !== "Pending") return;
    const review = (decision, reason = "") => frappe.call({
      method: "fieldpulse.scout_access.review_application",
      args: { application: frm.doc.name, decision, reason },
      freeze: true,
      callback: () => frm.reload_doc(),
    });
    frm.add_custom_button(__("Approve"), () => frappe.confirm(
      __("Approve this application, create the scout profile and enable sign-in?"), () => review("Approved")
    )).addClass("btn-primary");
    frm.add_custom_button(__("Reject"), () => frappe.prompt(
      { fieldname: "reason", fieldtype: "Small Text", label: __("Reason for rejection"), reqd: 1 },
      values => review("Rejected", values.reason), __("Reject scout application"), __("Reject")
    ));
  },
});
