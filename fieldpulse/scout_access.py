"""Scout admission and access decisions; only staff actions may change state."""
from contextlib import contextmanager

import frappe
from frappe.utils import now_datetime

REVIEW_ROLES = {"System Manager", "Admin", "Field Operations Coordinator"}
BLOCKED = {"Pending", "Rejected", "Deactivated"}


@contextmanager
def admission_write():
    previous = frappe.flags.dd_scout_admission_write
    frappe.flags.dd_scout_admission_write = True
    try:
        yield
    finally:
        frappe.flags.dd_scout_admission_write = previous


def require_reviewer():
    if frappe.session.user == "Guest" or not (
        frappe.session.user == "Administrator" or REVIEW_ROLES.intersection(frappe.get_roles())
    ):
        frappe.throw("Only scout admission reviewers can perform this action.", frappe.PermissionError)


def application_status(user):
    return frappe.db.get_value("Scout Application", {"user": user}, "status")


def can_create_profile(user):
    # Existing installations may still run the historical FP Agent conversion patch.
    # This exception cannot be selected by an HTTP caller or a document field.
    if (frappe.flags.in_migrate and not application_status(user)
            and frappe.db.exists("FP Agent", {"user": user})):
        return True
    return application_status(user) == "Approved"


def check_access(user):
    """Runs for password login and every authenticated request (including tokens)."""
    if not user or user in ("Guest", "Administrator"):
        return
    status = application_status(user)
    if status in BLOCKED:
        messages = {
            "Pending": "Your scout application is awaiting approval.",
            "Rejected": "Your scout application was rejected. Contact Diaspora Desk.",
            "Deactivated": "Your scout access has been deactivated. Contact Diaspora Desk.",
        }
        frappe.throw(messages[status], frappe.PermissionError)
    if frappe.db.get_value("Scout Profile", {"user": user}, "access_status") == "Deactivated":
        frappe.throw("Your scout access has been deactivated. Contact Diaspora Desk.", frappe.PermissionError)
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw("This account is disabled. Contact Diaspora Desk.", frappe.PermissionError)


def validate_auth():
    check_access(frappe.session.user)


def on_login(login_manager):
    check_access(login_manager.user)


def validate_user(doc, method=None):
    if doc.name in ("Guest", "Administrator"):
        return
    status = application_status(doc.name)
    inactive = frappe.db.get_value("Scout Profile", {"user": doc.name}, "access_status") == "Deactivated"
    if (status == "Deactivated" or inactive) and doc.enabled:
        frappe.throw("Use the Reactivate action on Scout Profile before enabling this user.")
    if status in BLOCKED and doc.enabled:
        frappe.throw("Scout access must be approved through Scout Applications before enabling this user.")
    if status in BLOCKED and any(row.role == "Field Agent" for row in doc.get("roles") or []):
        # Deactivated scouts retain historical roles but cannot be enabled.
        if status != "Deactivated":
            frappe.throw("Approve the scout application before assigning the Field Agent role.")


def protect_identity(doc, method=None, *args, **kwargs):
    if (frappe.db.exists("Scout Application", {"user": doc.name})
            or frappe.db.exists("Scout Profile", {"user": doc.name})):
        frappe.throw("Scout identities are retained for access decisions and audit. Deactivate the scout instead.")


def validate_application(doc):
    if not frappe.flags.dd_scout_admission_write:
        frappe.throw("Use the scout application approval or rejection actions.", frappe.PermissionError)


def validate_profile(doc):
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if doc.is_new() and not can_create_profile(doc.user):
        frappe.throw("Approve the scout application before creating a Scout Profile.")
    if previous and previous.user != doc.user:
        frappe.throw("A scout's linked user cannot be changed.")
    if not frappe.flags.dd_scout_admission_write:
        for key in ("access_status", "deactivated_by", "deactivated_at", "deactivation_reason",
                    "reactivated_by", "reactivated_at", "reactivation_reason"):
            if previous and previous.get(key) != doc.get(key):
                frappe.throw("Use the Deactivate or Reactivate action to change scout access.")
        if doc.is_new() and doc.get("access_status") != "Active":
            frappe.throw("New approved scouts must have Active access.")


def prevent_application_deletion(doc, method=None):
    frappe.throw("Scout applications are retained for access decisions and audit.")


def _locked_application(name):
    return frappe.get_doc("Scout Application", name, for_update=True)


def _decision(doc, status, reason):
    doc.status = status
    doc.reviewed_by = frappe.session.user
    doc.reviewed_at = now_datetime()
    doc.review_reason = reason
    doc.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def review_application(application, decision, reason=None):
    require_reviewer()
    if decision not in ("Approved", "Rejected"):
        frappe.throw("Choose Approve or Reject.")
    reason = (reason or "").strip()
    if decision == "Rejected" and not reason:
        frappe.throw("Enter a reason for rejection.")
    doc = _locked_application(application)
    if doc.status != "Pending":
        frappe.throw("This application has already been reviewed. Refresh the form.")
    with admission_write():
        _decision(doc, decision, reason)
        if decision == "Approved":
            user = frappe.get_doc("User", doc.user)
            user.enabled = 1
            user.append_roles("Field Agent")
            user.save(ignore_permissions=True)
            agent_name = frappe.db.exists("FP Agent", {"user": doc.user})
            agent = frappe.get_doc("FP Agent", agent_name) if agent_name else frappe.get_doc({
                "doctype": "FP Agent", "user": doc.user,
                "agent_code": f"AGT-{frappe.generate_hash(length=8).upper()}",
            })
            agent.full_name, agent.phone, agent.status = doc.full_name, doc.phone, "Active"
            agent.save(ignore_permissions=True)
            profile_name = frappe.db.exists("Scout Profile", {"user": doc.user})
            profile = frappe.get_doc("Scout Profile", profile_name) if profile_name else frappe.get_doc({
                "doctype": "Scout Profile", "user": doc.user,
                "availability_status": "Available", "access_status": "Active",
            })
            profile.scout_name, profile.base_county = doc.full_name, doc.county
            profile.phone_number, profile.legacy_fp_agent = doc.phone, agent.name
            profile.save(ignore_permissions=True)
            doc.scout_profile = profile.name
            doc.save(ignore_permissions=True)
    return {"status": doc.status, "scout_profile": doc.scout_profile}


@frappe.whitelist(methods=["POST"])
def deactivate_scout(scout_profile, reason):
    require_reviewer()
    reason = (reason or "").strip()
    if not reason:
        frappe.throw("Enter a reason for deactivation.")
    # Same lock used by assignment/leave changes prevents new assignments racing this action.
    profile = frappe.get_doc("Scout Profile", scout_profile, for_update=True)
    if not profile.user or profile.user in ("Administrator", "Guest", frappe.session.user):
        frappe.throw("This scout account cannot be deactivated with this action.")
    if profile.get("access_status") == "Deactivated":
        return {"status": "Deactivated"}
    app_name = frappe.db.exists("Scout Application", {"user": profile.user})
    application = _locked_application(app_name) if app_name else None
    if application and (application.status != "Approved" or application.scout_profile != profile.name):
        frappe.throw("Only approved scouts can be deactivated. Review the application first.")
    with admission_write():
        profile.access_status = "Deactivated"
        profile.deactivated_by, profile.deactivated_at = frappe.session.user, now_datetime()
        profile.deactivation_reason = reason
        profile.save(ignore_permissions=True)
        if application:
            application.status = "Deactivated"
            application.save(ignore_permissions=True)
        # Retain the User and profile so signup cannot recreate a blocked identity.
        user = frappe.get_doc("User", profile.user)
        user.enabled = 0
        user.api_key = None
        user.api_secret = None
        user.reset_password_key = None
        user.save(ignore_permissions=True)
        for name in frappe.get_all("FP Agent", filters={"user": profile.user}, pluck="name"):
            frappe.db.set_value("FP Agent", name, "status", "Suspended")
        frappe.clear_cache(user=profile.user)
        # Frappe session deletion commits internally, so run only after our atomic decision commits.
        from frappe.sessions import clear_sessions
        frappe.db.after_commit.add(lambda: clear_sessions(user=profile.user, force=True))
    return {"status": "Deactivated"}


@frappe.whitelist(methods=["POST"])
def reactivate_scout(scout_profile, reason):
    require_reviewer()
    reason = (reason or "").strip()
    if not reason:
        frappe.throw("Enter a reason for reactivation.")
    profile = frappe.get_doc("Scout Profile", scout_profile, for_update=True)
    if not profile.user or profile.user in ("Administrator", "Guest", frappe.session.user):
        frappe.throw("This scout account cannot be reactivated with this action.")
    if profile.get("access_status") != "Deactivated":
        frappe.throw("Only deactivated scouts can be reactivated. Refresh the form.")
    app_name = frappe.db.exists("Scout Application", {"user": profile.user})
    application = _locked_application(app_name) if app_name else None
    if application and (application.status not in ("Approved", "Deactivated")
                        or application.scout_profile != profile.name):
        frappe.throw("Reactivation cannot bypass scout application approval.")
    user = frappe.get_doc("User", profile.user, for_update=True)
    if not any(row.role == "Field Agent" for row in user.get("roles") or []):
        frappe.throw("This account no longer has the Field Agent role. Review its roles before reactivation.")
    with admission_write():
        profile.access_status = "Active"
        profile.reactivated_by, profile.reactivated_at = frappe.session.user, now_datetime()
        profile.reactivation_reason = reason
        # Leave, workload and the original deactivation/approval audit are retained.
        profile.save(ignore_permissions=True)
        if application:
            application.status = "Approved"
            application.save(ignore_permissions=True)
        for name in frappe.get_all("FP Agent", filters={"user": profile.user, "status": "Suspended"}, pluck="name"):
            frappe.db.set_value("FP Agent", name, "status", "Active")
        user.enabled = 1
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=profile.user)
    return {"status": "Active"}
