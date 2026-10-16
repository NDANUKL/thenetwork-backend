import frappe
from frappe.model.document import Document


class DDDispute(Document):
    def before_save(self):
        from fieldpulse.native_events import validate_dispute
        validate_dispute(self)
