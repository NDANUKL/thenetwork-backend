import frappe
from frappe.model.document import Document


class FPLocation(Document):
    def validate(self):
        if not isinstance(self.latitude, (int, float)) or not -90 <= self.latitude <= 90:
            frappe.throw("Latitude must be between -90 and 90")
        if not isinstance(self.longitude, (int, float)) or not -180 <= self.longitude <= 180:
            frappe.throw("Longitude must be between -180 and 180")
        if self.geofence_radius_m is not None and self.geofence_radius_m <= 0:
            frappe.throw("Geofence radius must be positive")
