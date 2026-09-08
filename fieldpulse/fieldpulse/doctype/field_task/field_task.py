import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from fieldpulse.fieldpulse.doctype.scout_profile.scout_profile import (
    recalculate_workload_and_availability,
)


STATUS_SEQUENCE = ("Assigned", "Accepted", "In Progress", "Submitted", "Approved")


class FieldTask(Document):
    """A scout allocation created from a Field Request."""

    def before_insert(self):
        self.assigned_at = self.assigned_at or now_datetime()

    def validate(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        self._validate_scout_assignment(previous)
        self._apply_status_transition(previous)

    def after_insert(self):
        self._sync_field_request_status()
        recalculate_workload_and_availability(self.scout_profile)

    def on_update(self):
        previous = self.get_doc_before_save()
        self._sync_field_request_status()
        if previous and previous.scout_profile != self.scout_profile:
            recalculate_workload_and_availability(previous.scout_profile)
        recalculate_workload_and_availability(self.scout_profile)

    def _validate_scout_assignment(self, previous):
        is_assignment = self.is_new() or (previous and previous.scout_profile != self.scout_profile)
        if not is_assignment:
            return
        if frappe.db.get_value("Scout Profile", self.scout_profile, "availability_status") == "On Leave":
            frappe.throw("A task cannot be assigned to a scout who is On Leave")

    def _apply_status_transition(self, previous):
        if not previous or previous.status == self.status:
            return

        old_status = previous.status
        if self.status == "Cancelled":
            if old_status == "Approved":
                frappe.throw("An approved task cannot be cancelled")
            return

        if self.status == "Rejected":
            if old_status != "Submitted":
                frappe.throw("Only a submitted task can be rejected for rework")
            self.status = "In Progress"
            self.rework_count = (previous.rework_count or 0) + 1
            return

        if old_status not in STATUS_SEQUENCE or self.status not in STATUS_SEQUENCE:
            frappe.throw(f"Invalid task status transition from {old_status} to {self.status}")
        if STATUS_SEQUENCE.index(self.status) != STATUS_SEQUENCE.index(old_status) + 1:
            frappe.throw(f"Invalid task status transition from {old_status} to {self.status}")

        timestamp_field = {
            "Accepted": "accepted_at",
            "In Progress": "started_at",
            "Submitted": "submitted_at",
            "Approved": "completed_at",
        }.get(self.status)
        if timestamp_field and not self.get(timestamp_field):
            self.set(timestamp_field, now_datetime())

    def _sync_field_request_status(self):
        if not self.field_request:
            return
        request_status = {
            "Assigned": "Assigned",
            "Accepted": "Assigned",
            "In Progress": "In Progress",
            "Submitted": "In Progress",
            "Approved": "Completed",
            "Cancelled": "Cancelled",
        }.get(self.status)
        if request_status:
            frappe.db.set_value("Field Request", self.field_request, "status", request_status)


def _require_allocation_permission(field_request):
    if not frappe.has_permission("Field Request", "write", field_request):
        frappe.throw("Not permitted to allocate this Field Request", frappe.PermissionError)
    if not frappe.has_permission("Field Task", "create"):
        frappe.throw("Not permitted to create Field Tasks", frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def assign_field_request(field_request, scout_profile, questionnaire=None, location=None, due_at=None):
    """Allocate a Field Request to an available scout."""
    _require_allocation_permission(field_request)
    if not questionnaire or not location:
        frappe.throw("A questionnaire and location are required to allocate a Field Task")
    if frappe.db.get_value("Scout Profile", scout_profile, "availability_status") == "On Leave":
        frappe.throw("A task cannot be assigned to a scout who is On Leave")
    if frappe.db.exists(
        "Field Task",
        {"field_request": field_request, "status": ["not in", ["Cancelled"]]},
    ):
        frappe.throw("This Field Request already has an active Field Task")

    questionnaire_version = (
        frappe.db.get_value("FP Questionnaire", questionnaire, "version") if questionnaire else None
    )
    due_at = due_at or frappe.db.get_value("Field Request", field_request, "deadline")
    task = frappe.get_doc(
        {
            "doctype": "Field Task",
            "field_request": field_request,
            "scout_profile": scout_profile,
            "questionnaire": questionnaire,
            "questionnaire_version": questionnaire_version,
            "location": location,
            "due_at": due_at,
            "status": "Assigned",
        }
    )
    task.insert()
    return {"field_task": task.name}


@frappe.whitelist(methods=["POST"])
def reassign_field_task(field_task, scout_profile, reason):
    """Move a task to another available scout and preserve the audit trail."""
    if not frappe.has_permission("Field Task", "write", field_task):
        frappe.throw("Not permitted to reassign this Field Task", frappe.PermissionError)
    if not (reason or "").strip():
        frappe.throw("A reassignment reason is required")

    task = frappe.get_doc("Field Task", field_task)
    if task.scout_profile == scout_profile:
        return {"field_task": task.name, "status": "unchanged"}
    if frappe.db.get_value("Scout Profile", scout_profile, "availability_status") == "On Leave":
        frappe.throw("A task cannot be assigned to a scout who is On Leave")

    task.append(
        "reassignment_history",
        {
            "from_scout": task.scout_profile,
            "to_scout": scout_profile,
            "reassigned_by": frappe.session.user,
            "reassigned_at": now_datetime(),
            "reason": reason.strip(),
        },
    )
    task.scout_profile = scout_profile
    task.save()
    return {"field_task": task.name, "status": "reassigned"}


def _get_current_scout_task(field_task):
    task = frappe.get_doc("Field Task", field_task)
    scout_profile = frappe.db.exists("Scout Profile", {"user": frappe.session.user})
    if not scout_profile or task.scout_profile != scout_profile:
        frappe.throw("This Field Task is not assigned to the current scout", frappe.PermissionError)
    return task


@frappe.whitelist(methods=["POST"])
def accept_field_task(field_task):
    """Allow the assigned scout to accept an allocated task."""
    task = _get_current_scout_task(field_task)
    if task.status != "Assigned":
        frappe.throw("Only an assigned task can be accepted")
    task.status = "Accepted"
    task.save(ignore_permissions=True)
    return {"field_task": task.name, "status": task.status, "accepted_at": task.accepted_at}


@frappe.whitelist(methods=["POST"])
def start_field_task(field_task):
    """Mark an accepted task in progress when the scout starts responding."""
    task = _get_current_scout_task(field_task)
    if task.status != "Accepted":
        frappe.throw("Only an accepted task can be started")
    task.status = "In Progress"
    task.save(ignore_permissions=True)
    return {"field_task": task.name, "status": task.status, "started_at": task.started_at}
