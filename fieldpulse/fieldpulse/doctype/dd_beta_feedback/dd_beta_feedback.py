import frappe
from frappe.model.document import Document


class DDBetaFeedback(Document):
    def validate(self):
        if not self.is_new() or not self.flags.get("beta_feedback_submission"):
            frappe.throw("Beta feedback responses cannot be edited or created manually", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Beta feedback responses must be retained", frappe.PermissionError)
