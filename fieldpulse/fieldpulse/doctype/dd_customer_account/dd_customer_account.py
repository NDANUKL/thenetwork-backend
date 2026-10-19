import frappe
from frappe.model.document import Document

class DDCustomerAccount(Document):
    def before_insert(self):
        if not self.get("beta_access"):
            from fieldpulse.beta_access import registration_access
            self.beta_access = "Pending" if registration_access() == "Invite only" else "Approved"

    def validate(self):
        if self.get("beta_access") not in (None, "", "Pending", "Approved", "Rejected"):
            frappe.throw("Choose a valid beta access status")
        if not self.is_new() and self.has_value_changed("beta_access"):
            if "System Manager" not in frappe.get_roles():
                frappe.throw("Only System Managers can change beta access", frappe.PermissionError)
            if self.beta_access == "Approved":
                self.approval_email_id = frappe.generate_hash(length=32)
                self.approval_email_sent_at = None
            else:
                self.approval_email_id = None
                self.approval_email_sent_at = None

    def on_update(self):
        if self.get("approval_email_id") and not self.get("approval_email_sent_at"):
            frappe.enqueue("fieldpulse.access_notifications.send_approval", account_name=self.name,
                           enqueue_after_commit=True)
