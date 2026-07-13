import frappe
from frappe.model.document import Document


class FPTask(Document):
    def validate(self):
        if self.consent_status in ("Pending", "Declined", "Revoked") and self.status == "Assigned":
            frappe.throw("A task cannot be assigned before consent is granted")

