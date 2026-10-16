import frappe
from frappe.model.document import Document


class DDServiceReport(Document):
    def before_save(self):
        from fieldpulse.native_events import validate_report
        validate_report(self)
