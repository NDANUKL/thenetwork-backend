frappe.ui.form.on("DD Service Report", {
  setup(frm) {
    // Keep keyboard printing on the same client PDF as the preview button.
    frm.print_doc = () => frm.events.preview_report_pdf(frm);
    $(frm.wrapper).on('attachments_change.dd_service_report', () => frm.attachments?.parent.hide());
  },
  refresh(frm) {
    frm.toolbar.print_icon?.hide();
    frm.page.menu.find('.menu-item-label').filter(function () {
      return $(this).text().trim() === __('Print');
    }).closest('li').remove();
    frm.attachments?.parent.hide();
    if (frm.is_new()) return;
    frm.add_custom_button(__("Preview report PDF"), () => frm.events.preview_report_pdf(frm));
    if (frm.doc.status === "Approved") return;
    frm.set_intro(__("Draft reports are private. Review the scout answers and selected evidence, then use Preview report PDF. Set Status to Approved and save to release the report and selected evidence to the client."));
    frm.add_custom_button(__('Refresh from approved findings'),()=>frappe.confirm(__('Refresh the Task Brief findings and evidence selections from approved submissions? Coordinator remarks are retained.'),async()=>{
      if (frm.is_dirty()) await frm.save();
      await frappe.call('fieldpulse.scout_reports.refresh_draft',{report:frm.doc.name});
      await frm.reload_doc();
    }));
  },
  async preview_report_pdf(frm) {
    if (frm.is_new()) return;
    // Open during the click so browsers allow the tab after the async request.
    const preview = window.open('about:blank', '_blank');
    if (preview) preview.opener = null;
    try {
      if (frm.is_dirty()) await frm.save();
      const {message} = await frappe.call({
        method: 'fieldpulse.scout_reports.preview_pdf',
        args: {report: frm.doc.name}, freeze: true,
        freeze_message: __('Preparing report preview...'),
      });
      if (!message?.file?.startsWith('/private/files/')) throw new Error(__('Report PDF is unavailable.'));
      if (preview) preview.location.replace(message.file);
      else frappe.msgprint(__('Allow pop-ups for this site, then click Preview report PDF again.'));
      await frm.reload_doc();
    } catch (error) {
      if (preview) preview.close();
      throw error;
    }
  }
});

frappe.ui.form.on("DD Report Evidence", {
  async preview(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    const {message} = await frappe.call("fieldpulse.evidence.get_evidence_view_url", {evidence_id: row.evidence});
    frappe.msgprint({title: __("Reviewed evidence"), message: `<p>${frappe.utils.escape_html(row.caption || "")}</p><a href="${frappe.utils.escape_html(message.view_url)}" target="_blank" rel="noopener noreferrer">${__("Open photo or video")}</a>`});
  }
});
