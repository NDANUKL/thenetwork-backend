frappe.ui.form.on("DD Service Report", {
  refresh(frm) {
    if (frm.is_new() || frm.doc.status === "Approved") return;
    frm.set_intro(__("Review the findings from the coordinator-approved questionnaire and the scout submission. Acknowledge each Not verified limitation and confirm coverage. Select the permitted client photos and videos, review their captions, explain limitations, then generate the PDF before approval. Approval publishes the report in the client portal."));
    frm.add_custom_button(__('Refresh from approved findings'),()=>frappe.confirm(__('Replace this draft summary, question findings, limitations and evidence selections from approved records? Saved next steps are retained. The draft uses the exact questions assigned to the scout.'),async()=>{
      if (frm.is_dirty()) await frm.save();
      await frappe.call('fieldpulse.scout_reports.refresh_draft',{report:frm.doc.name});
      await frm.reload_doc();
    }));
    frm.add_custom_button(__("Generate report PDF"), async () => {
      if (frm.is_dirty()) await frm.save();
      await frappe.call("fieldpulse.scout_reports.generate_pdf", {report: frm.doc.name});
      await frm.reload_doc();
    });
  }
});

frappe.ui.form.on("DD Report Evidence", {
  async preview(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const {message} = await frappe.call("fieldpulse.evidence.get_evidence_view_url", {evidence_id: row.evidence});
    frappe.msgprint({title: __("Reviewed evidence"), message: `<p>${frappe.utils.escape_html(row.caption || "")}</p><a href="${frappe.utils.escape_html(message.view_url)}" target="_blank" rel="noopener noreferrer">${__("Open photo or video")}</a>`});
  }
});
