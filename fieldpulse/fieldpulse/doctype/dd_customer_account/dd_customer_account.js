frappe.ui.form.on("DD Customer Account", {
  refresh(frm) {
    if (frm.is_new() || (frappe.session.user !== "Administrator" && !frappe.user.has_role("System Manager"))) return;
    const inactive = frm.doc.account_access === "Deactivated";
    const action = inactive ? "Reactivate" : "Deactivate";
    if (frm.doc.user) frm.add_custom_button(__(action), () => {
      if (frm.is_dirty()) return frappe.msgprint(__("Save or discard your changes before changing account access."));
      frappe.prompt(
        { fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1,
          description: inactive
            ? __("Restores account activation. Existing approval and email-verification requirements still apply. The client must sign in again.")
            : __("Blocks sign-in and revokes current sessions. Requests, payments and approval decisions are retained.") },
        values => frappe.call({
          method: "fieldpulse.customer_access.set_account_access",
          args: { account: frm.doc.name, action, reason: values.reason }, freeze: true,
          callback: () => frm.reload_doc(),
        }), __(action + " client account"), __(action)
      );
    });
    if (inactive) frm.set_intro(__("This client account is deactivated. Granting approval does not reactivate the account."), "red");
    const status = frm.doc.beta_access || "Approved";
    const change = (label, status) => frm.add_custom_button(__(label), () => {
      frm.set_value("beta_access", status).then(() => frm.save());
    });
    if (status !== "Approved") change("Grant access", "Approved");
    if (status === "Approved") change("Remove access", "Pending");
    if (status !== "Rejected") change("Reject", "Rejected");
  }
});
