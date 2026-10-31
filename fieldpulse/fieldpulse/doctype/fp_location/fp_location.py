import frappe
from frappe.model.document import Document


class FPLocation(Document):
    def validate(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and self.geofence_radius_m != previous.geofence_radius_m:
            frappe.throw('Geofence radius cannot be changed after location creation')
        try:
            latitude, longitude = float(self.latitude), float(self.longitude)
        except (TypeError, ValueError):
            frappe.throw("Enter valid latitude and longitude coordinates")
        if not -90 <= latitude <= 90:
            frappe.throw("Latitude must be between -90 and 90")
        if not -180 <= longitude <= 180:
            frappe.throw("Longitude must be between -180 and 180")
        if self.geofence_radius_m is not None and self.geofence_radius_m <= 0:
            frappe.throw("Geofence radius must be positive")

    def on_update(self):
        previous = self.get_doc_before_save()
        if not previous:
            return
        try:
            coordinates_changed = (
                float(previous.latitude) != float(self.latitude)
                or float(previous.longitude) != float(self.longitude)
            )
        except (TypeError, ValueError):
            coordinates_changed = True
        if not coordinates_changed:
            return

        # A Field Task stores an immutable client-facing pin in its Task Brief
        # snapshot. Keep still-unstarted assignments aligned when a coordinator
        # corrects the operational FP Location directly in Desk. Updating the
        # task's modified timestamp makes the normal mobile delta sync deliver it.
        from fieldpulse.project_locations import refresh_assigned_task_pins
        refresh_assigned_task_pins(self)
