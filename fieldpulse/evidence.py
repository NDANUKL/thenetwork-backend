"""Private Cloudflare R2 evidence storage helpers and API endpoints."""

import os

import boto3
import frappe
from botocore.client import Config
from frappe.utils import now_datetime


PRESIGNED_URL_EXPIRY_SECONDS = 15 * 60
EVIDENCE_VIEW_ROLES = {"Admin", "Supervisor", "Field Operations Coordinator"}


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
    captured_at=None,
    gps_lat=None,
    gps_lng=None,
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
    settings = _r2_settings()
    evidence_name = frappe.db.exists("Field Evidence", {"client_uuid": client_uuid})

    if evidence_name:
        evidence = frappe.get_doc("Field Evidence", evidence_name)
        if evidence.scout != scout_profile or evidence.field_task != field_task:
            frappe.throw("The client upload ID belongs to another evidence record", frappe.PermissionError)
        if evidence.upload_status == "Uploaded":
            return {"evidence_id": evidence.name, "upload_status": evidence.upload_status}
    else:
        evidence = frappe.get_doc(
            {
                "doctype": "Field Evidence",
                "client_uuid": client_uuid,
                "field_task": field_task,
                "scout": scout_profile,
                "evidence_type": evidence_type,
                "r2_object_key": _object_key(field_task, client_uuid, filename),
                "original_filename": os.path.basename(filename),
                "mime_type": mime_type,
                "file_size": int(file_size),
                "captured_at": captured_at,
                "gps_lat": gps_lat,
                "gps_lng": gps_lng,
                "upload_status": "Pending",
            }
        )
        evidence.insert(ignore_permissions=True)

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
    scout_profile = _current_scout()
    if evidence.scout != scout_profile:
        frappe.throw("This evidence does not belong to the current scout", frappe.PermissionError)

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
    if object_metadata.get("ContentLength") != evidence.file_size:
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
    if not EVIDENCE_VIEW_ROLES.intersection(frappe.get_roles()):
        frappe.throw("Not permitted to view field evidence", frappe.PermissionError)

    evidence = frappe.get_doc("Field Evidence", evidence_id)
    if evidence.upload_status != "Uploaded":
        frappe.throw("Evidence is not available for viewing")
    settings = _r2_settings()
    view_url = _r2_client(settings).generate_presigned_url(
        "get_object",
        Params={"Bucket": settings["bucket"], "Key": evidence.r2_object_key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )
    return {"evidence_id": evidence.name, "view_url": view_url, "expires_in_seconds": PRESIGNED_URL_EXPIRY_SECONDS}
