import frappe
from frappe.model.document import Document


class DiasporaRequest(Document):
    def before_insert(self):
        from fieldpulse.task_brief_jobs import initialise
        initialise(self)
