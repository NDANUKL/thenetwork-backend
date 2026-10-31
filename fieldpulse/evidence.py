"""Private Cloudflare R2 evidence storage helpers and API endpoints."""

import os

import boto3
import frappe
from botocore.client import Config
from frappe.utils import now_datetime
from fieldpulse.mobile_datetime import mobile_datetime


PRESIGNED_URL_EXPIRY_SECONDS = 15 * 60
EVIDENCE_VIEW_ROLES = {"Admin", "Supervisor", "System Manager", "Field Operations Coordinator"}
QUESTION_ATTACHMENT_EVIDENCE_TYPES = {
    "photo": "Photo",
    "file_attachment": "Document",
    "signature": "Signature",
}


def _r2_settings():
    configured = frappe.conf.get("r2_environment")
    if configured in {"dev", "prod"}:
        environment = configured
    else:
        dev_ready = all(frappe.conf.get(f"r2_dev_{key}") for key in _r2_keys())
        prod_ready = all(frappe.conf.get(f"r2_prod_{key}") for key in _r2_keys())
        if dev_ready == prod_ready:
            frappe.throw(
                "R2 storage is ambiguous or incomplete. Set r2_environment to dev or prod."
            )
        environment = "dev" if dev_ready else "prod"

    settings = {key: frappe.conf.get(f"r2_{environment}_{key}") for key in _r2_keys()}
    missing = [key for key, value in settings.items() if not value]
    if missing:
        frappe.throw(f"R2 {environment} configuration is missing: {', '.join(missing)}")
    return settings


def _r2_keys():
    return ("access_key_id", "secret_access_key", "endpoint", "bucket")


def _r2_client(settings=None):
    settings = settings or _r2_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings["endpoint"],
        aws_access_key_id=settings["access_key_id"],
        aws_secret_access_key=settings["secret_access_key"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _current_scout():
    scout_profile = frappe.db.exists("Scout Profile", {"user": frappe.session.user})
    if not scout_profile:
        frappe.throw("No Scout Profile is linked to the current user", frappe.PermissionError)
    return scout_profile


def _assert_scout_owns_task(field_task, scout_profile):
    if frappe.db.get_value("Field Task", field_task, "scout_profile") != scout_profile:
        frappe.throw("This Field Task is not assigned to the current scout", frappe.PermissionError)


def _object_key(field_task, client_uuid, filename):
    return f"field-evidence/{field_task}/{client_uuid}/{os.path.basename(filename)}"


def _normalise_etag(etag):
    return (etag or "").strip().strip('"')


@frappe.whitelist(methods=["POST"])
def request_evidence_upload(
    field_task,
    client_uuid,
    filename,
    mime_type,
    file_size,
    evidence_type,
    question_response=None,
    captured_at=None,
    gps_lat=None,
    gps_lng=None,
    caption=None,
    accuracy_m=None,
    metadata_origin=None,
    location_sampled_at=None,
    description=None,
    clarification_required=0,
    task_response=None,
    field_check_id=None,
):
    """Create/reuse evidence metadata and return a short-lived R2 PUT URL."""
    if not client_uuid:
        frappe.throw("A client upload ID is required")
    if not filename or not os.path.basename(filename):
        frappe.throw("A filename is required")
    if not mime_type:
        frappe.throw("A MIME type is required")
    if not evidence_type:
        frappe.throw("An evidence type is required")
    if int(file_size or 0) <= 0:
        frappe.throw("File size must be greater than zero")

    scout_profile = _current_scout()
    _assert_scout_owns_task(field_task, scout_profile)
    frappe.db.sql('SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE', [field_task])
    brief_task = frappe.get_doc('Field Task', field_task)
    if not brief_task.get('task_brief_version'):
        frappe.throw('Historical questionnaire evidence is read-only. Use a Task Brief.')
    if brief_task.get('task_brief_version'):
        from fieldpulse.task_brief_workflow import snapshot, decoded
        from fieldpulse.task_briefs import gps_result
        if question_response or not task_response or not field_check_id:
            frappe.throw('Task Brief evidence must identify its submission and field check')
        response = frappe.get_doc('FP Task Response', task_response)
        pinned = snapshot(brief_task)
        if response.task != field_task or response.agent != scout_profile or response.status != 'Draft' or field_check_id not in pinned['check_ids']:
            frappe.throw('Evidence must belong to this scout\'s open assigned check', frappe.PermissionError)
        if gps_result(decoded(response.arrival_check_json, {}), pinned['site'])['status'] != 'inside':
            frappe.throw('Verify arrival before collecting field evidence')
        gallery = metadata_origin == 'Gallery' and evidence_type in ('Photo', 'Video')
        if not gallery and (metadata_origin != 'Camera' or evidence_type not in ('Photo', 'Video')):
            frappe.throw('Use an app capture or matching device-library media for coordinator review')
        if gallery:
            # Selecting a file now does not establish its original capture provenance.
            captured_at = gps_lat = gps_lng = accuracy_m = location_sampled_at = None
            clarification_required = 1
        else:
            if not captured_at:
                frappe.throw('Keep the original evidence capture timestamp')
            from datetime import timedelta
            captured = mobile_datetime(captured_at)
            if not captured or captured > frappe.utils.now_datetime() + timedelta(minutes=5):
                frappe.throw('The capture timestamp is invalid or in the future')
    if evidence_type in {"Photo", "Video"} and not mime_type.startswith("image/" if evidence_type == "Photo" else "video/"):
        frappe.throw("Evidence media type does not match its content type")
    settings = _r2_settings()
    evidence_name = frappe.db.exists("Field Evidence", {"client_uuid": client_uuid})

    if evidence_name:
        evidence = frappe.get_doc("Field Evidence", evidence_name)
        if evidence.scout != scout_profile or evidence.field_task != field_task:
            frappe.throw("The client upload ID belongs to another evidence record", frappe.PermissionError)
        if (evidence.question_response or "") != (question_response or ""):
            frappe.throw("The client upload ID belongs to another question response", frappe.PermissionError)
        if (evidence.get('task_response') or '') != (task_response or '') or (evidence.get('field_check_id') or '') != (field_check_id or ''):
            frappe.throw('The upload ID belongs to another field check', frappe.PermissionError)
        if evidence.upload_status == "Uploaded":
            return {"evidence_id": evidence.name, "upload_status": evidence.upload_status}
    else:
        evidence = frappe.get_doc(
            {
                "doctype": "Field Evidence",
                "client_uuid": client_uuid,
                "field_task": field_task,
                "scout": scout_profile,
                "question_response": question_response,
                "task_response": task_response,
                "field_check_id": field_check_id,
                "evidence_type": evidence_type,
                "r2_object_key": _object_key(field_task, client_uuid, filename),
                "original_filename": os.path.basename(filename),
                "mime_type": mime_type,
                "file_size": int(file_size),
                "captured_at": mobile_datetime(captured_at),
                "gps_lat": gps_lat,
                "gps_lng": gps_lng,
                "caption": str(caption or "")[:2000],
                "accuracy_m": accuracy_m,
                "metadata_origin": metadata_origin,
                "location_sampled_at": mobile_datetime(location_sampled_at),
                "description": str(description or '')[:2000],
                "clarification_required": int(str(clarification_required).lower() in {'1','true'}),
                "upload_status": "Pending",
            }
        )
        evidence.insert(ignore_permissions=True)

    if frappe.db.get_value("Field Task", field_task, "status") in ("Submitted", "Approved", "Rejected", "Cancelled"):
        frappe.throw("Evidence is frozen after submission; request rework", frappe.PermissionError)

    upload_url = _r2_client(settings).generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings["bucket"],
            "Key": evidence.r2_object_key,
            "ContentType": evidence.mime_type,
        },
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        HttpMethod="PUT",
    )
    if evidence.upload_status != "Uploading":
        frappe.db.set_value("Field Evidence", evidence.name, "upload_status", "Uploading")
    frappe.db.commit()
    return {
        "evidence_id": evidence.name,
        "upload_url": upload_url,
        "headers": {"Content-Type": evidence.mime_type},
        "expires_in_seconds": PRESIGNED_URL_EXPIRY_SECONDS,
        "upload_status": "Uploading",
    }


@frappe.whitelist(methods=["POST"])
def confirm_evidence_upload(evidence_id, etag):
    """Verify the uploaded private object before marking evidence uploaded."""
    evidence = frappe.get_doc("Field Evidence", evidence_id)
    frappe.db.sql('SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE', [evidence.field_task])
    scout_profile = _current_scout()
    if evidence.scout != scout_profile:
        frappe.throw("This evidence does not belong to the current scout", frappe.PermissionError)

    _assert_scout_owns_task(evidence.field_task, scout_profile)
    if evidence.upload_status == "Uploaded":
        return {"evidence_id": evidence.name, "upload_status": "Uploaded", "etag": evidence.etag}
    if not frappe.db.get_value('Field Task', evidence.field_task, 'task_brief_version'):
        frappe.throw('Historical questionnaire evidence is read-only. Use a Task Brief.')
    if frappe.db.get_value("Field Task", evidence.field_task, "status") in ("Submitted", "Approved", "Rejected", "Cancelled"):
        frappe.throw("Evidence is frozen after submission; request rework", frappe.PermissionError)
    settings = _r2_settings()
    try:
        object_metadata = _r2_client(settings).head_object(
            Bucket=settings["bucket"], Key=evidence.r2_object_key
        )
    except Exception:
        frappe.db.set_value("Field Evidence", evidence.name, "upload_status", "Failed")
        frappe.db.commit()
        frappe.throw("Evidence object could not be verified in R2")

    received_etag = _normalise_etag(object_metadata.get("ETag"))
    if not received_etag or received_etag != _normalise_etag(etag):
        frappe.db.set_value("Field Evidence", evidence.name, "upload_status", "Failed")
        frappe.db.commit()
        frappe.throw("Evidence integrity check failed")
    if int(object_metadata.get("ContentLength")) != int(evidence.file_size):
        frappe.db.set_value("Field Evidence", evidence.name, "upload_status", "Failed")
        frappe.db.commit()
        frappe.throw("Evidence file size does not match the requested upload")

    frappe.db.set_value(
        "Field Evidence",
        evidence.name,
        {"upload_status": "Uploaded", "etag": received_etag},
    )
    if not frappe.db.get_value("Field Task", evidence.field_task, "first_evidence_at"):
        frappe.db.set_value("Field Task", evidence.field_task, "first_evidence_at", now_datetime())
    frappe.db.commit()
    return {"evidence_id": evidence.name, "upload_status": "Uploaded", "etag": received_etag}


@frappe.whitelist()
def get_evidence_view_url(evidence_id):
    """Return a short-lived GET URL to an authorized Desk user."""
    evidence = frappe.get_doc("Field Evidence", evidence_id)
    if not EVIDENCE_VIEW_ROLES.intersection(frappe.get_roles()):
        scout = _current_scout()
        if evidence.scout != scout:
            frappe.throw("Not permitted to view field evidence", frappe.PermissionError)
        _assert_scout_owns_task(evidence.field_task, scout)
    if evidence.upload_status != "Uploaded":
        frappe.throw("Evidence is not available for viewing")
    settings = _r2_settings()
    view_url = _r2_client(settings).generate_presigned_url(
        "get_object",
        Params={"Bucket": settings["bucket"], "Key": evidence.r2_object_key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )
    return {"evidence_id": evidence.name, "view_url": view_url, "expires_in_seconds": PRESIGNED_URL_EXPIRY_SECONDS}
