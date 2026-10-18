"""Scout-owned mobile profile and leave settings."""
import frappe
from frappe.utils import now_datetime

ACTIVE_TASK_STATUSES = ("Assigned", "Accepted", "In Progress")


def profile_permission(doc, ptype=None, user=None, **kwargs):
    user = user or frappe.session.user
    if user != "Administrator" and "Field Operations Coordinator" in frappe.get_roles(user):
        if ptype in ("write", "create", "delete", "submit", "cancel", "amend", "share"):
            return False
    return None


def _own_profile():
    user = frappe.session.user
    if (user == "Guest" or not frappe.db.get_value("User", user, "enabled")
            or "Field Agent" not in frappe.get_roles(user)):
        frappe.throw("Sign in as an active scout.", frappe.PermissionError)
    name = frappe.db.exists("Scout Profile", {"user": user})
    if not name:
        frappe.throw("No scout profile is linked to this account.", frappe.PermissionError)
    return frappe.get_doc("Scout Profile", name)


def _payload(profile):
    return {key: profile.get(key) for key in (
        "scout_name", "base_county", "phone_number", "availability_status",
        "activity_status", "active_task_count", "completed_task_count")}


@frappe.whitelist(methods=["GET"])
def get_profile():
    return _payload(_own_profile())


@frappe.whitelist(methods=["POST"])
def update_profile(full_name=None, county=None, phone=None, on_leave=None):
    profile = _own_profile()
    # Serialize leave changes with assignments, which also lock Scout Profile.
    frappe.db.sql("SELECT name FROM `tabScout Profile` WHERE name=%s FOR UPDATE", (profile.name,))
    profile.reload()
    if full_name is not None:
        full_name = " ".join(full_name.split())
        if (len(full_name.split()) < 2 or len(full_name) > 140
                or not all(any(c.isalpha() for c in part) for part in full_name.split())
                or any(c in full_name for c in "<>")):
            frappe.throw("Enter your full name (at least two names).")
        profile.scout_name = full_name
    if county is not None:
        county = " ".join(county.split())
        if not county or len(county) > 100 or any(c in county for c in "<>"):
            frappe.throw("Enter your county (up to 100 characters).")
        profile.base_county = county
    if phone is not None:
        phone = phone.strip()
        if len(phone) > 40 or any(c not in "+0123456789 ()-" for c in phone):
            frappe.throw("Enter a valid phone number (up to 40 characters).")
        profile.phone_number = phone
    if on_leave is not None:
        if not isinstance(on_leave, bool):
            frappe.throw("Choose whether you are on leave.")
        active = frappe.db.count("Field Task", {
            "scout_profile": profile.name, "status": ["in", ACTIVE_TASK_STATUSES],
        })
        profile.active_task_count = active
        profile.availability_status = "On Leave" if on_leave else ("Busy" if active else "Available")
    profile.last_app_activity = now_datetime()
    profile.activity_status = "Active"
    profile.flags.scout_self_service = True
    profile.save(ignore_permissions=True)
    # Keep login name and legacy agent contact data aligned with the mobile profile.
    if full_name is not None:
        user = frappe.get_doc("User", frappe.session.user)
        user.first_name = full_name.split()[0]
        user.middle_name = ""
        user.last_name = " ".join(full_name.split()[1:])
        user.save(ignore_permissions=True)
    if profile.legacy_fp_agent and (full_name is not None or phone is not None):
        agent = frappe.get_doc("FP Agent", profile.legacy_fp_agent)
        if full_name is not None:
            agent.full_name = full_name
        if phone is not None:
            agent.phone = phone
        agent.save(ignore_permissions=True)
    return _payload(profile)
