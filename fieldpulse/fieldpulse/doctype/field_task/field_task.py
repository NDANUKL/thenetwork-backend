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
        from fieldpulse.task_numbers import next_task_number
        self.task_number = next_task_number()
        self.assigned_at = self.assigned_at or now_datetime()

    def validate(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and not previous.get('task_brief_version') and self.get('task_brief_version'):
            frappe.throw('Create a new allocation to assign a Task Brief')
        if previous and previous.get('task_brief_version'):
            from fieldpulse.task_brief_workflow import validate_task
            validate_task(self, previous)
        if self.is_new() and self.get('replaces_task') and frappe.flags.dd_replacement_source != self.replaces_task:
            frappe.throw('Use the coordinator rework action to create a replacement assignment')
        if previous and self.get('replaces_task') != previous.get('replaces_task'):
            frappe.throw('Replacement assignment provenance cannot be changed')
        if previous and self.get("task_number") != previous.get("task_number"):
            frappe.throw("Task numbers cannot be changed")
        if previous and previous.get("questionnaire") == self.get("questionnaire"):
            self.questionnaire_version = previous.get("questionnaire_version")
        else:
            self.questionnaire_version = frappe.db.get_value("FP Questionnaire", self.questionnaire, "version") if self.get("questionnaire") else 0
        if previous and previous.get("questionnaire_scope"):
            for key in ("questionnaire", "questionnaire_scope", "client_request_snapshot"):
                if self.get(key) != previous.get(key):
                    frappe.throw("An assigned questionnaire and request snapshot cannot be changed")
            if self.status == "Approved" and previous.status != "Approved":
                if not frappe.db.exists("FP Task Response", {"task": self.name, "status": "Submitted", "qa_status": "Passed", "reviewed_by": ["is", "set"]}):
                    frappe.throw("Review and approve the scout submission before completing this task")
        if previous and previous.scout_profile != self.scout_profile and (previous.get('rework_response') or previous.get('revisit_request')):
            frappe.throw('A rework response belongs to its assigned scout; create a separate revisit assignment instead')
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
        frappe.db.sql("SELECT name FROM `tabScout Profile` WHERE name=%s FOR UPDATE", (self.scout_profile,))
        if frappe.db.get_value("Scout Profile", self.scout_profile, "access_status", for_update=True) == "Deactivated":
            frappe.throw("A task cannot be assigned to a deactivated scout")
        if frappe.db.get_value("Scout Profile", self.scout_profile, "availability_status") == "On Leave":
            frappe.throw("A task cannot be assigned to a scout who is On Leave")

    def _apply_status_transition(self, previous):
        if not previous or previous.status == self.status:
            return

        old_status = previous.status
        if self.status == "Cancelled":
            if old_status == 'Awaiting authorization' and self.get('revisit_request'):
                revisit_status = frappe.db.get_value('DD Revisit Request', self.revisit_request, 'status')
                if revisit_status in ('Awaiting authorization', 'Authorized') and frappe.flags.dd_authorized_revisit != self.revisit_request:
                    frappe.throw('Close or dispatch the pending revisit authorization before cancelling its task')
            if old_status == "Approved":
                frappe.throw("An approved task cannot be cancelled")
            return

        if self.status == 'Awaiting authorization':
            if old_status != 'Submitted' or not frappe.flags.dd_pending_revisit_response:
                frappe.throw('Use the submission review to record a revisit request')
            self.rework_count = (previous.rework_count or 0) + 1
            return
        if old_status == 'Awaiting authorization':
            if self.status != 'In Progress' or not self.get('revisit_request') or frappe.flags.dd_authorized_revisit != self.revisit_request:
                frappe.throw('Authorize and dispatch the revisit before restarting work')
            return
        if self.status == "Rejected":
            if self.get('rework_type') == 'Return to site': frappe.throw('Site revisits require authorization before dispatch')
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
        from fieldpulse.native_ownership import native_enabled
        from fieldpulse.project_alignment import rollup_tasks

        if native_enabled("DD Task Completion Rollup"):
            rollup_tasks(self)


def _require_allocation_permission(field_request):
    if not frappe.has_permission("Field Request", "write", field_request):
        frappe.throw("Not permitted to allocate this Field Request", frappe.PermissionError)
    if not frappe.has_permission("Field Task", "create"):
        frappe.throw("Not permitted to create Field Tasks", frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def assign_field_request(field_request, scout_profile, questionnaire=None, location=None, due_at=None):
    """Allocate a Field Request to an available scout."""
    from fieldpulse.project_alignment import assign_project_scouts

    result = assign_project_scouts(field_request, [{
        "scout": scout_profile, "questionnaire": questionnaire, "location": location,
    }])
    if due_at:
        task = frappe.get_doc("Field Task", result["tasks"][0])
        task.due_at = due_at
        task.save()
    return {"field_task": result["tasks"][0]}


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
    if frappe.db.get_value("Field Task", {
        "field_request": task.field_request,
        "scout_profile": scout_profile,
        "submission_review_status": "Reject",
    }, "name"):
        frappe.throw("This scout was rejected for this project and cannot be assigned to it again. Choose another scout.")
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
