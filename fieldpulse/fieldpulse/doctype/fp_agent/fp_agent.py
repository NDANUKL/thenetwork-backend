import frappe
from frappe.model.document import Document


class FPAgent(Document):
    def validate(self):
        if self.service_radius_km is not None and self.service_radius_km < 0:
            frappe.throw("Service radius cannot be negative")

