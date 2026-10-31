import frappe
from frappe.model.document import Document

from fieldpulse.utils import haversine_distance_m
from fieldpulse.geofence import effective_geofence_radius


class FPTaskResponse(Document):
    def validate(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        if self.is_new() and self.get('rework_of') and frappe.flags.dd_rework_response_uuid != self.client_uuid:
            frappe.throw('Only the coordinator rework action may create a revision')
        if previous:
            for key in ('rework_of', 'rework_type', 'rework_questions_json'):
                if self.get(key) != previous.get(key): frappe.throw('Rework provenance cannot be changed')
        if previous and previous.status == "Submitted":
            for key in ('brief_answers_json', 'brief_completion_json'):
                if self.get(key) != previous.get(key):
                    frappe.throw('Submitted field checks are immutable')
            for key in ("task", "agent", "location", "status", "arrival_check_json", "final_review_json", "latitude", "longitude", "accuracy_m", "submitted_at", "started_at", "client_uuid", "device_id", "app_version", "client_updated_at", "geofence_status", "geofence_distance_m", "rejection_reason"):
                if self.get(key) != previous.get(key):
                    frappe.throw("Submitted scout findings are immutable; request rework for a new response")
            for key in ("qa_status", "review_status", "review_reasons", "reviewed_by", "reviewed_at", "review_notes"):
                if self.get(key) != previous.get(key):
                    frappe.throw("Use the coordinator review actions to record a review")
            return
        if "Field Agent" in frappe.get_roles() and not {"System Manager", "Field Operations Coordinator", "Supervisor", "Admin"}.intersection(frappe.get_roles()):
            task = frappe.get_doc("Field Task", self.task)
            scout = frappe.db.exists("Scout Profile", {"user": frappe.session.user})
            if not scout or self.agent != scout or task.scout_profile != scout:
                frappe.throw("Not your assigned task", frappe.PermissionError)
            if self.get("qa_status") not in (None, "", "Pending", previous.get("qa_status") if previous else "Pending") or self.get("reviewed_by") or self.get("review_notes"):
                frappe.throw("Only coordinators can review submissions", frappe.PermissionError)
        if self.is_new() and frappe.db.get_value("Field Task", self.task, "status") in ("Submitted", "Approved", "Rejected", "Cancelled"):
            frappe.throw("This task is no longer open for new responses")
        self._apply_geofence_check()
        from fieldpulse.scout_submissions import validate_submission
        managed = validate_submission(self)
        self._sync_task_status()

    def _apply_geofence_check(self):
        if not self.location or self.latitude is None or self.longitude is None:
            self.geofence_status = "Invalid GPS"
            return
        location = frappe.get_doc("FP Location", self.location)
        distance = haversine_distance_m(
            float(self.latitude), float(self.longitude), float(location.latitude), float(location.longitude)
        )
        self.geofence_distance_m = distance
        self.geofence_status = "Inside" if distance <= effective_geofence_radius(location.geofence_radius_m) else "Outside"


    def _sync_task_status(self):
        # Pre-creating a blank replacement revision must not mark the new scout
        # as having accepted or started fieldwork.
        if self.status == 'Draft' and frappe.flags.dd_rework_response_uuid == self.client_uuid:
            return
        if not self.task:
            return
        task = frappe.get_doc("Field Task", self.task)

        # A first saved response is an implicit acceptance/start for legacy
        # clients that save a draft before calling the explicit accept action.
        if self.status == "Draft":
            if task.status == "Assigned":
                task = self._transition_field_task(task, "Accepted")
            if task.status == "Accepted":
                self._transition_field_task(task, "In Progress")
            return

        if self.status != "Submitted" or task.status in ("Submitted", "Approved", "Rejected"):
            return
        if task.status == "Assigned":
            task = self._transition_field_task(task, "Accepted")
        if task.status == "Accepted":
            task = self._transition_field_task(task, "In Progress")
        if task.status != "In Progress":
            frappe.throw(f"Cannot submit Field Task while it is {task.status}")
        self._transition_field_task(task, "Submitted")

    @staticmethod
    def _transition_field_task(task, status):
        """Persist through Field Task hooks so derived state remains current."""
        task.status = status
        task.save(ignore_permissions=True)
        return frappe.get_doc("Field Task", task.name)
