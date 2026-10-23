if (frappe.boot.dd_native_handover_active) {
frappe.ui.form.on("DD Quotation", {
  setup(frm) {
    frm.set_query("field_request", "items", () => ({ filters: { diaspora_request: frm.doc.request } }));
  },
  refresh(frm) {
    frm.set_df_property("terms", "hidden", 1);
    frm.set_df_property("currency", "read_only", 1);
    if (frm.is_new()) frm.set_value("currency", "USD");
  },
  discount_type(frm) {
    frm.set_df_property("discount_value", "description", frm.doc.discount_type === "Percentage"
      ? "Percentage of the combined project subtotal (0?100)."
      : "Amount in the quotation currency, deducted before VAT.");
  }
});
frappe.ui.form.on("DD Quotation Item", {
  items_add(frm, cdt, cdn) {
    frappe.model.set_value(cdt, cdn, { quantity: 1, rate: 100 });
  }
});
// DD Quotation Withdrawal
frappe.ui.form.on("DD Quotation", { refresh(frm) { if (!frm.is_new() && frm.doc.status === "Issued" && frm.perm.some(p => p.write)) { frm.add_custom_button("Withdraw quotation", () => frappe.confirm("Withdraw this unaccepted quotation? You can then prepare its replacement.", async () => { const proof = await frappe.xcall("dd_payments", {action:"csrf"}); await frappe.xcall("dd_payments", {action:"withdraw_quote", quote:frm.doc.name, portal_csrf_token:proof.mutation_token}); await frm.reload_doc(); })); } } });

}
