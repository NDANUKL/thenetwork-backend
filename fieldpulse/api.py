"""
Whitelisted sync API endpoints for the FieldPulse mobile client.

Follows the pull-then-push batch sync contract from the Week 2 build
spec: mobile pulls assignments by delta timestamp, then pushes
structured responses and attachments separately, each keyed by a
client-generated UUID for idempotency.
"""

import frappe
from frappe.utils import now_datetime

from fieldpulse.utils import haversine_distance_m


def _get_agent_for_user(user=None):
    user = user or frappe.session.user
    agent_name = frappe.db.exists("FP Agent", {"user": user})
    if not agent_name:
        frappe.throw(f"No FP Agent record linked to user {user}")
    return frappe.get_doc("FP Agent", agent_name)


@frappe.whitelist()
def sync_pull_assignments(since=None):
    """Return tasks (and referenced locations/questionnaires/questions)
    assigned to the calling agent, changed since the given timestamp."""
    agent = _get_agent_for_user()

    filters = {"agent": agent.name}
    if since:
        filters["server_updated_at"] = [">", since]

    tasks = frappe.get_all("FP Task", filters=filters, fields=["*"])

    location_names = list({t["location"] for t in tasks if t.get("location")})
    questionnaire_names = list({t["questionnaire"] for t in tasks if t.get("questionnaire")})

    locations = (
        frappe.get_all("FP Location", filters={"name": ["in", location_names]}, fields=["*"])
        if location_names else []
    )
    questionnaires = (
        frappe.get_all("FP Questionnaire", filters={"name": ["in", questionnaire_names]}, fields=["*"])
        if questionnaire_names else []
    )

    questions = []
    options = []
    if questionnaire_names:
        questions = frappe.get_all(
            "FP Question", filters={"questionnaire": ["in", questionnaire_names]}, fields=["*"]
        )
        question_names = [q["name"] for q in questions]
        if question_names:
            options = frappe.get_all(
                "FP Question Option", filters={"question": ["in", question_names]}, fields=["*"]
            )

    return {
        "tasks": tasks,
        "locations": locations,
        "questionnaires": questionnaires,
        "questions": questions,
        "question_options": options,
        "server_time": now_datetime().isoformat(),
    }


@frappe.whitelist(methods=["POST"])
def sync_push_responses(batch):
    """Accept a batch of Task Response / Question Response records.
    Each item must include a client_uuid. Idempotent: retried UUIDs
    return the existing record instead of creating a duplicate."""
    if isinstance(batch, str):
        batch = frappe.parse_json(batch)

    accepted = []
    rejected = []

    for item in batch.get("task_responses", []):
        try:
            accepted.append(_upsert_task_response(item))
        except Exception as e:
            rejected.append({"client_uuid": item.get("client_uuid"), "errors": [str(e)]})

    for item in batch.get("question_responses", []):
        try:
            accepted.append(_upsert_question_response(item))
        except Exception as e:
            rejected.append({"client_uuid": item.get("client_uuid"), "errors": [str(e)]})

    frappe.db.commit()
    return {"accepted": accepted, "rejected": rejected}


def _upsert_task_response(item):
    client_uuid = item.get("client_uuid")
    if not client_uuid:
        frappe.throw("Missing client_uuid")

    existing = frappe.db.exists("FP Task Response", {"client_uuid": client_uuid})
    if existing:
        doc = frappe.get_doc("FP Task Response", existing)
        incoming_ts = item.get("client_updated_at")
        if incoming_ts and doc.client_updated_at and incoming_ts <= str(doc.client_updated_at):
            return {"client_uuid": client_uuid, "server_id": doc.name, "status": "already_exists"}
    else:
        doc = frappe.new_doc("FP Task Response")
        doc.client_uuid = client_uuid

    for field in (
        "task", "agent", "location", "status", "started_at", "submitted_at",
        "client_updated_at", "device_id", "app_version",
        "latitude", "longitude", "accuracy_m",
    ):
        if field in item:
            doc.set(field, item[field])

    _apply_geofence_check(doc)
    doc.save(ignore_permissions=True)
    return {"client_uuid": client_uuid, "server_id": doc.name, "status": "accepted"}


def _apply_geofence_check(doc):
    if not (doc.location and doc.latitude and doc.longitude):
        doc.geofence_status = "Invalid GPS"
        return

    location = frappe.get_doc("FP Location", doc.location)
    distance = haversine_distance_m(doc.latitude, doc.longitude, location.latitude, location.longitude)
    doc.geofence_distance_m = distance
    doc.geofence_status = "Inside" if distance <= (location.geofence_radius_m or 50) else "Outside"


def _upsert_question_response(item):
    client_uuid = item.get("client_uuid")
    if not client_uuid:
        frappe.throw("Missing client_uuid")

    existing = frappe.db.exists("FP Question Response", {"client_uuid": client_uuid})
    if existing:
        doc = frappe.get_doc("FP Question Response", existing)
        incoming_ts = item.get("client_updated_at")
        if incoming_ts and doc.client_updated_at and incoming_ts <= str(doc.client_updated_at):
            return {"client_uuid": client_uuid, "server_id": doc.name, "status": "already_exists"}
    else:
        doc = frappe.new_doc("FP Question Response")
        doc.client_uuid = client_uuid

    for field in (
        "task_response", "question", "question_code", "question_type",
        "answer_text", "answer_json", "client_updated_at",
    ):
        if field in item:
            doc.set(field, item[field])

    doc.save(ignore_permissions=True)
    return {"client_uuid": client_uuid, "server_id": doc.name, "status": "accepted"}


@frappe.whitelist(methods=["POST"])
def sync_upload_attachment(
    client_uuid, task_response, attachment_type, file_url,
    mime_type=None, file_size_bytes=None, question_response=None,
    captured_at=None, latitude=None, longitude=None, accuracy_m=None,
):
    """Idempotent, append-only attachment upload. Existing client_uuid
    returns success without overwriting the stored file."""
    existing = frappe.db.exists("FP Attachment", {"client_uuid": client_uuid})
    if existing:
        return {"client_uuid": client_uuid, "server_id": existing, "status": "already_exists"}

    doc = frappe.new_doc("FP Attachment")
    doc.client_uuid = client_uuid
    doc.task_response = task_response
    doc.question_response = question_response
    doc.attachment_type = attachment_type
    doc.file_url = file_url
    doc.mime_type = mime_type
    doc.file_size_bytes = file_size_bytes
    doc.captured_at = captured_at
    doc.latitude = latitude
    doc.longitude = longitude
    doc.accuracy_m = accuracy_m
    doc.upload_status = "Uploaded"
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {"client_uuid": client_uuid, "server_id": doc.name, "status": "accepted"}


@frappe.whitelist(methods=["POST"])
def sync_log(agent=None, device_id=None, direction="Mixed", status="Success",
             pulled_count=0, pushed_count=0, accepted_count=0, rejected_count=0,
             error_count=0, summary_json=None):
    """Record a sync session summary for debugging/audit."""
    if not agent:
        agent = _get_agent_for_user().name

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
