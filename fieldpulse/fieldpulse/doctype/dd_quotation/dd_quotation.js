if (frappe.boot.dd_native_handover_active) {
function updateDiscountPreview(frm) {
  const draft = frm.doc.status === "Draft" || frm.is_new();
  const subtotal = draft ? (frm.doc.items || []).length * 100 : Number(frm.doc.subtotal || 0);
  let discount = Number(frm.doc.discount_value || 0);
  if (frm.doc.discount_type === "Percentage") discount = Math.round(subtotal * discount) / 100;
  if (draft && frm.doc.discount_type !== "Fixed amount") {
    frm.doc.discount_value = discount;
    frm.doc.discount_type = "Fixed amount";
    frm.refresh_field("discount_value");
    frm.refresh_field("discount_type");
    frm.dirty();
  }
  const percentage = subtotal > 0 ? Math.round(discount / subtotal * 10000) / 100 : 0;
  frm.doc.discount_percentage = percentage;
  frm.refresh_field("discount_percentage");
  frm.set_df_property("discount_value", "description", `Amount deducted before VAT. This is ${percentage.toFixed(2)}% of the project subtotal.`);
}

frappe.ui.form.on("DD Quotation", {
  setup(frm) {
    frm.set_query("field_request", "items", () => ({ filters: { diaspora_request: frm.doc.request } }));
  },
  refresh(frm) {
    frm.set_df_property("terms", "hidden", 1);
    frm.set_df_property("currency", "read_only", 1);
    if (frm.is_new()) frm.set_value("currency", "USD");
    frm.trigger("discount_type");
  },
  discount_type(frm) { updateDiscountPreview(frm); },
  discount_value(frm) { updateDiscountPreview(frm); }

});
function updateDeadlinePreview(frm) {
  const rows = frm.doc.items || [];
  const dates = rows.map(row => row.agreed_work_deadline).filter(Boolean).sort();
  frm.set_value("agreed_completion_date", dates.length && dates.length === rows.length ? dates[dates.length - 1] : null);
}
frappe.ui.form.on("DD Quotation Item", {
  async field_request(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const selected = row.field_request;
    const response = selected ? await frappe.db.get_value("Field Request", selected, "deadline") : null;
    if (row.field_request !== selected) return;
    await frappe.model.set_value(cdt, cdn, "agreed_work_deadline", response?.message?.deadline || null);
    updateDeadlinePreview(frm);
  },
  agreed_work_deadline(frm) { updateDeadlinePreview(frm); },
  items_remove(frm) { updateDiscountPreview(frm); updateDeadlinePreview(frm); },
  items_add(frm, cdt, cdn) {
    frappe.model.set_value(cdt, cdn, { quantity: 1, rate: 100 });
    updateDiscountPreview(frm);
  }
});
// DD Quotation Withdrawal
frappe.ui.form.on("DD Quotation", { refresh(frm) { if (!frm.is_new() && frm.doc.status === "Issued" && frm.perm.some(p => p.write)) { frm.add_custom_button("Withdraw quotation", () => frappe.confirm("Withdraw this unaccepted quotation? You can then prepare its replacement.", async () => { const proof = await frappe.xcall("dd_payments", {action:"csrf"}); await frappe.xcall("dd_payments", {action:"withdraw_quote", quote:frm.doc.name, portal_csrf_token:proof.mutation_token}); await frm.reload_doc(); })); } } });

}
