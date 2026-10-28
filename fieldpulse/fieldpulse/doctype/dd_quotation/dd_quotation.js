if (frappe.boot.dd_native_handover_active) {
function pricing(frm) {
  return frm.doc.pricing_mode === 'Beta - KSh 1 per project'
    ? { currency: 'KES', rate: 1, inclusive: 1 }
    : { currency: 'USD', rate: 100, inclusive: 0 };
}
async function applyPricing(frm, resetDiscount = false) {
  if (!frm.is_new() && frm.doc.status !== 'Draft') return;
  const price = pricing(frm);
  await frm.set_value({ currency: price.currency, tax_inclusive: price.inclusive,
    ...(resetDiscount ? { discount_value: 0, discount_type: 'Fixed amount' } : {}) });
  for (const row of frm.doc.items || []) {
    await frappe.model.set_value(row.doctype, row.name, { quantity: 1, rate: price.rate, amount: price.rate });
  }
  frm.refresh_field('items');
  updateDiscountPreview(frm);
}
function updateDiscountPreview(frm) {
  const draft = frm.doc.status === "Draft" || frm.is_new();
  const subtotal = draft ? (frm.doc.items || []).filter(row => row.field_request).length * pricing(frm).rate : Number(frm.doc.subtotal || 0);
  let discount = Number(frm.doc.discount_value || 0);
  if (frm.doc.discount_type === "Percentage") discount = Math.round(subtotal * discount) / 100;
  if (draft && frm.doc.discount_type !== "Fixed amount") {
    frm.doc.discount_value = discount;
    frm.doc.discount_type = "Fixed amount";
    frm.refresh_field("discount_value");
    frm.refresh_field("discount_type");
    frm.dirty();
  }
  // Refresh totals when changing currency/rate; server validation remains authoritative.
  if (draft) {
    const round = value => Math.round((value + Number.EPSILON) * 100) / 100;
    const net = round(subtotal - discount);
    const vatRate = Number(frm.doc.vat_rate ?? 16);
    if (Number.isFinite(net) && net >= 0 && Number.isFinite(vatRate) && vatRate >= 0 && vatRate <= 100) {
      const taxable = pricing(frm).inclusive ? round(net / (1 + vatRate / 100)) : net;
      const vat = pricing(frm).inclusive ? round(net - taxable) : round(taxable * vatRate / 100);
      const total = round(taxable + vat);
      const deposit = round(total / 2);
      Object.assign(frm.doc, { subtotal, discount_amount: discount, taxable_amount: taxable,
        vat_amount: vat, total, deposit_amount: deposit, balance_amount: round(total - deposit) });
      for (const field of ['subtotal', 'discount_amount', 'taxable_amount', 'vat_amount', 'total', 'deposit_amount', 'balance_amount']) frm.refresh_field(field);
    }
  }
  const percentage = subtotal > 0 ? Math.round(discount / subtotal * 10000) / 100 : 0;
  frm.doc.discount_percentage = percentage;
  frm.refresh_field("discount_percentage");
  frm.set_df_property("discount_value", "description", `Discount in ${frm.doc.currency}. This is ${percentage.toFixed(2)}% of the project subtotal.`);
}

frappe.ui.form.on("DD Quotation", {
  setup(frm) {
    frm.set_query('field_request', 'items', (_doc, _cdt, cdn) => {
      const used = (frm.doc.items || []).filter(row => row.name !== cdn && row.field_request).map(row => row.field_request);
      return { filters: { diaspora_request: frm.doc.request || '', ...(used.length ? { name: ['not in', used] } : {}) } };
    });
  },
  async refresh(frm) {
    frm.set_df_property("terms", "hidden", 1);
    frm.set_df_property("currency", "read_only", 1);
    frm.set_df_property('pricing_mode', 'read_only', !frm.is_new() && frm.doc.status !== 'Draft');
    if (frm.is_new()) {
      if (!frm.doc.pricing_mode) await frm.set_value('pricing_mode', 'Live - USD 100 per project');
      await applyPricing(frm);
    }
    frm.trigger("discount_type");
  },
  pricing_mode(frm) { return applyPricing(frm, true); },
  validate(frm) {
    const seen = new Set();
    for (const row of frm.doc.items || []) {
      if (row.field_request && seen.has(row.field_request)) frappe.throw('Each project can appear only once. Remove the duplicate row.');
      if (row.field_request) seen.add(row.field_request);
    }
  },
  discount_type(frm) { updateDiscountPreview(frm); },
  discount_value(frm) { updateDiscountPreview(frm); },
  vat_rate(frm) { updateDiscountPreview(frm); }

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
    if (selected && (frm.doc.items || []).some(other => other.name !== cdn && other.field_request === selected)) {
      await frappe.model.set_value(cdt, cdn, { field_request: null, agreed_work_deadline: null });
      updateDiscountPreview(frm);
      updateDeadlinePreview(frm);
      frappe.msgprint('This project is already in the quotation. Select a different project.');
      return;
    }
    const response = selected ? await frappe.db.get_value("Field Request", selected, "deadline") : null;
    if (row.field_request !== selected) return;
    await frappe.model.set_value(cdt, cdn, "agreed_work_deadline", response?.message?.deadline || null);
    updateDeadlinePreview(frm);
    updateDiscountPreview(frm);
  },
  agreed_work_deadline(frm) { updateDeadlinePreview(frm); },
  items_remove(frm) { updateDiscountPreview(frm); updateDeadlinePreview(frm); },
  items_add(frm, cdt, cdn) {
    frappe.model.set_value(cdt, cdn, { quantity: 1, rate: pricing(frm).rate, amount: pricing(frm).rate });
    updateDiscountPreview(frm);
  }
});
// DD Quotation Withdrawal
frappe.ui.form.on("DD Quotation", { refresh(frm) { if (!frm.is_new() && frm.doc.status === "Issued" && frm.perm.some(p => p.write)) { frm.add_custom_button("Withdraw quotation", () => frappe.confirm("Withdraw this unaccepted quotation? You can then prepare its replacement.", async () => { const proof = await frappe.xcall("dd_payments", {action:"csrf"}); await frappe.xcall("dd_payments", {action:"withdraw_quote", quote:frm.doc.name, portal_csrf_token:proof.mutation_token}); await frm.reload_doc(); })); } } });

}
