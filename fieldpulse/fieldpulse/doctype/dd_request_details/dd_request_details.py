import frappe
from frappe.model.document import Document


class DDRequestDetails(Document):
    def before_save(self):
        from fieldpulse.request_details import validate
        validate(self)

    def on_update(self):
        from fieldpulse.request_details import update_next_action
        update_next_action(self)
