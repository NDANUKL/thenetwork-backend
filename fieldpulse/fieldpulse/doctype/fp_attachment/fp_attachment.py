import frappe
from frappe.model.document import Document


class FPAttachment(Document):
    def before_save(self):
        if not self.is_new():
            frappe.throw("Attachments are append-only and cannot be modified after creation")

