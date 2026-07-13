import frappe
from frappe.model.document import Document


class FPLocation(Document):
    def validate(self):
        if self.latitude is None or not -90 <= float(self.latitude) <= 90:
            frappe.throw("Latitude must be between -90 and 90")
        if self.longitude is None or not -180 <= float(self.longitude) <= 180:
            frappe.throw("Longitude must be between -180 and 180")
        if self.geofence_radius_m is not None and self.geofence_radius_m <= 0:
            frappe.throw("Geofence radius must be positive")

