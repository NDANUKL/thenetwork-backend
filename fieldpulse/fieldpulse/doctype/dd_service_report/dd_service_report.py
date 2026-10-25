import frappe
from frappe.model.document import Document


class DDServiceReport(Document):
    def before_save(self):
        from fieldpulse.native_events import validate_report
        from fieldpulse.report_preparation import validate_snapshot
        validate_snapshot(self)
        validate_report(self)
