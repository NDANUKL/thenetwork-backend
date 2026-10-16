import frappe
from frappe.model.document import Document


class DDQuotation(Document):
    def before_save(self):
        from fieldpulse.native_events import validate_quote
        validate_quote(self)
