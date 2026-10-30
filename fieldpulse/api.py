"""
Whitelisted sync API endpoints for the FieldPulse mobile client.

Follows the pull-then-push batch sync contract from the Week 2 build
spec: mobile pulls assignments by delta timestamp, then pushes
structured responses, each keyed by a client-generated UUID for idempotency.
Evidence is uploaded through the separate R2 presigned-URL flow in
``fieldpulse.evidence``.
"""

import frappe
from frappe.utils import now_datetime

from fieldpulse.utils import haversine_distance_m
from fieldpulse.geofence import effective_geofence_radius
from fieldpulse.mobile_datetime import mobile_datetime, site_datetime_iso


def _get_scout_profile_for_user(user=None):
    user = user or frappe.session.user
    scout_profile = frappe.db.exists("Scout Profile", {"user": user})
    if not scout_profile:
        frappe.throw(f"No Scout Profile record linked to user {user}")
    return frappe.get_doc("Scout Profile", scout_profile)


def _mobile_capabilities():
    # Increment the contract only for changes that require a coordinated mobile release.
    return {"contract": 1, "protocol_version": 2, "visit_workflow_version": 2,
            "rework_version": 2, "questionnaire_editor_version": 1,
            "authoritative_assignments": True, "resumable_submission": True, "task_brief_version": 1}


@frappe.whitelist()
def sync_pull_assignments(since=None, protocol_version=1, visit_workflow_version=0, rework_version=0, questionnaire_editor_version=0, task_brief_version=0):
    """Return tasks (and referenced locations/questionnaires/questions)
    assigned to the calling scout, changed since the given timestamp."""
    scout_profile = _get_scout_profile_for_user()

    # Fail before returning an authoritative list that would hide ongoing work.
    from fieldpulse.task_brief_cutover import open_legacy_tasks, cancelled_legacy_tasks
    if open_legacy_tasks(scout_profile.name):
        frappe.throw('Task Brief cutover is pending for your existing assignments. Contact your coordinator. Saved work has not been withdrawn or changed.')

    frappe.db.set_value("Scout Profile", scout_profile.name, {
        "last_app_activity": now_datetime(), "activity_status": "Active",
    }, update_modified=False)

    filters = {"scout_profile": scout_profile.name, "task_brief_version": ["is", "set"]}
    if since:
        filters["modified"] = [">", since]

    server_time = now_datetime().isoformat()
    tasks = frappe.get_all("Field Task", filters=filters, fields=["*"])
    # Closed historical work is still part of this scout's assignment history.
    # A fresh install must receive the same approved records an older device
    # retained locally. Do not republish questionnaires or convert their pins.
    historical_filters = {
        "scout_profile": scout_profile.name,
        "status": "Approved",
        "task_brief_version": ["is", "not set"],
    }
    if since:
        historical_filters["modified"] = [">", since]
    known = {task['name'] for task in tasks}
    tasks.extend(task for task in frappe.get_all("Field Task", filters=historical_filters, fields=["*"])
                 if task['name'] not in known)
    known = {task['name'] for task in tasks}
    tasks.extend(task for task in cancelled_legacy_tasks(scout_profile.name, since) if task['name'] not in known)
    if int(task_brief_version or 0) < 1 and any(task.get('task_brief_version') for task in tasks):
        frappe.throw('Update Ground Scouts to open the approved Task Briefs. Saved work remains on this device.')
    if int(visit_workflow_version or 0) < 2 and any((frappe.parse_json(task.get('client_request_snapshot') or '{}') or {}).get('visit_workflow_version') == 2 for task in tasks):
        frappe.throw('Update the app to use the verified-arrival visit workflow. Saved work remains on this device.')
    if int(protocol_version or 1) < 2 and any((frappe.parse_json(task.get('client_request_snapshot') or '{}') or {}).get('protocol_version') == 2 for task in tasks):
        frappe.throw('Update the DiasporaDesk app to open the streamlined questionnaires. Saved work remains on your device.')
    if int(rework_version or 0) < 1 and any(task.get('rework_response') and task.status in ('Assigned', 'Accepted', 'In Progress') for task in tasks):
        frappe.throw('Update the scout app to open response revisions. Your saved work remains on this device.')
    if int(rework_version or 0) < 2 and any(task.status == 'Awaiting authorization' for task in tasks):
        frappe.throw('Update the scout app to view revisit authorization holds. Do not start held work.')
    if int(questionnaire_editor_version or 0) < 1 and any((frappe.parse_json(task.get('client_request_snapshot') or '{}') or {}).get('project_questionnaire') for task in tasks):
        frappe.throw('Update the scout app to use the project-specific questionnaire. Saved work remains on this device.')
    for task in tasks:
        task["server_updated_at"] = site_datetime_iso(task.get("modified"))
        for field in ("due_at", "assigned_at", "creation", "created_at"):
            if task.get(field):
                task[field] = site_datetime_iso(task[field])
        if task.get('task_brief_version'):
            from fieldpulse.task_brief_workflow import revision_payload
            task['brief_revision'] = revision_payload(task)

    location_names = list({t["location"] for t in tasks if t.get("location")})
    locations = (
        frappe.get_all("FP Location", filters={"name": ["in", location_names]}, fields=["*"])
        if location_names else []
    )
    # Empty legacy envelopes allow queued historical data to remain local without
    # redistributing questionnaire templates or predefined questions.
    questionnaires, questions, options = [], [], []

    # Older mobile builds pull with GET, so explicitly persist the activity stamp.
    frappe.db.commit()

    from fieldpulse.scout_inbox import notification_payload
    return {
        "notifications": notification_payload(),
        "capabilities": _mobile_capabilities(),
        "full_snapshot": not bool(since),
        "assigned_task_ids": [task["name"] for task in tasks] if not since else None,
        "tasks": tasks,
        "locations": locations,
        "questionnaires": questionnaires,
        "questions": questions,
        "question_options": options,
        "server_time": server_time,
    }


@frappe.whitelist(methods=["POST"])
def sync_log(agent=None, device_id=None, direction="Mixed", status="Success",
             pulled_count=0, pushed_count=0, accepted_count=0, rejected_count=0,
             error_count=0, summary_json=None):
    """Record a sync session summary for debugging/audit."""
    current_scout = _get_scout_profile_for_user()
    if agent and agent != current_scout.name:
        frappe.throw("Sync logs can only be recorded for the current scout")
    agent = current_scout.name

    doc = frappe.new_doc("FP Sync Log")
    doc.sync_session_id = frappe.generate_hash(length=12)
    doc.agent = agent
    doc.device_id = device_id
    doc.started_at = now_datetime()
    doc.completed_at = now_datetime()
    doc.direction = direction
    doc.status = status
    doc.pulled_count = pulled_count
    doc.pushed_count = pushed_count
    doc.accepted_count = accepted_count
    doc.rejected_count = rejected_count
    doc.error_count = error_count
    doc.summary_json = summary_json
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"sync_session_id": doc.sync_session_id}
