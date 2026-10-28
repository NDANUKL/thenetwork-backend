"""Read-only historical record. New fieldwork uses DD Task Brief."""
import frappe
from frappe.model.document import Document

class FPQuestion(Document):
    def validate(self):
        frappe.throw('Historical questionnaire records are read-only. Use a Task Brief.')

    def on_trash(self):
        frappe.throw('Historical questionnaire records must be retained for audit.')
