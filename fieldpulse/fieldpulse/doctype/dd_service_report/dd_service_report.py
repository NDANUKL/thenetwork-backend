import frappe
from frappe.model.document import Document


class DDServiceReport(Document):
    def before_save(self):
        from fieldpulse.native_events import validate_report
        from fieldpulse.report_preparation import validate_snapshot
        validate_snapshot(self)
        previous = self.get_doc_before_save()
        if self.status == 'Approved' and (not previous or previous.status != 'Approved'):
            if self.is_new():
                frappe.throw('Save the draft before approving the report')
            from fieldpulse.scout_reports import prepare_pdf
            prepare_pdf(self, save=False)
        validate_report(self)
