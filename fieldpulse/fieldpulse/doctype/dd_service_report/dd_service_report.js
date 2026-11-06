frappe.ui.form.on("DD Service Report", {
  refresh(frm) {
    if (frm.is_new()) return;
    if (frm.doc.report_file?.startsWith('/private/files/')) {
      frm.add_custom_button(__("Preview report PDF"), () => window.open(frm.doc.report_file, '_blank', 'noopener,noreferrer'));
    }
    if (frm.doc.status === "Approved") return;
    frm.set_intro(__("Review the Task Brief and scout answers, choose which photos and videos to share, and optionally add coordinator remarks. Generate the PDF before approving the report for the client."));
    frm.add_custom_button(__('Refresh from approved findings'),()=>frappe.confirm(__('Refresh the Task Brief findings and evidence selections from approved submissions? Coordinator remarks are retained.'),async()=>{
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
