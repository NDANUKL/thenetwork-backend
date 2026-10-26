import frappe
from frappe.model.document import Document


class ScoutDataRequest(Document):
    def validate(self):
        staff = frappe.session.user == 'Administrator' or bool({'System Manager', 'Admin'}.intersection(frappe.get_roles()))
        previous = self.get_doc_before_save()
        if self.is_new():
            if not staff and not frappe.flags.scout_data_request:
                frappe.throw('Use the verified account data request flow.', frappe.PermissionError)
            self.status = 'Open'
        elif not staff:
            frappe.throw('Only privacy administrators may update this request.', frappe.PermissionError)
        if previous and (self.user != previous.user or self.reason != previous.reason):
            frappe.throw('The original account and request reason are immutable.')
        if self.status not in ('Open', 'Under review', 'Completed', 'Declined'):
            frappe.throw('Invalid request status.')
        if self.status in ('Completed', 'Declined') and not (self.public_reply or '').strip():
            frappe.throw('Explain the outcome and any retained records before closing the request.')
        if len(self.reason or '') > 1000:
            frappe.throw('Reason must be at most 1000 characters.')

    def on_update(self):
        previous=self.get_doc_before_save()
        if previous and (self.status!=previous.status or (self.public_reply or '')!=(previous.public_reply or '')):
            frappe.get_doc(dict(doctype='Notification Log',for_user=self.user,from_user=frappe.session.user,
                type='Alert',subject='Privacy request updated',email_content='Your privacy request has an update. Open Privacy for its status and response.',
                document_type=self.doctype,document_name=self.name)).insert(ignore_permissions=True)
