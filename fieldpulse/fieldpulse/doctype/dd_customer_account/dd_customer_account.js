frappe.ui.form.on("DD Customer Account", {
  refresh(frm) {
    if (frm.is_new() || !frappe.user.has_role("System Manager")) return;
    const status = frm.doc.beta_access || "Approved";
    const change = (label, status) => frm.add_custom_button(__(label), () => {
      frm.set_value("beta_access", status).then(() => frm.save());
    });
    if (status !== "Approved") change("Grant access", "Approved");
    if (status === "Approved") change("Remove access", "Pending");
    if (status !== "Rejected") change("Reject", "Rejected");
  }
});
