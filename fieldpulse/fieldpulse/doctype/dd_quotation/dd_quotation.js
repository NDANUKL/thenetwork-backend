if (frappe.boot.dd_native_handover_active) {
// DD Quotation Withdrawal
frappe.ui.form.on("DD Quotation", { refresh(frm) { if (!frm.is_new() && frm.doc.status === "Issued" && frm.perm.some(p => p.write)) { frm.add_custom_button("Withdraw quotation", () => frappe.confirm("Withdraw this unaccepted quotation? You can then prepare its replacement.", async () => { const proof = await frappe.xcall("dd_payments", {action:"csrf"}); await frappe.xcall("dd_payments", {action:"withdraw_quote", quote:frm.doc.name, portal_csrf_token:proof.mutation_token}); await frm.reload_doc(); })); } } });

}
