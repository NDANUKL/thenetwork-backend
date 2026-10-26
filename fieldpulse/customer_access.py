"""Client account activation is independent from beta approval and verification."""
from contextlib import contextmanager

import frappe
from frappe.utils import now_datetime

ACCESS_FIELDS = (
    "account_access", "deactivated_by", "deactivated_at", "deactivation_reason",
    "reactivated_by", "reactivated_at", "reactivation_reason",
)


@contextmanager
def access_write():
    previous = frappe.flags.dd_customer_access_write
    frappe.flags.dd_customer_access_write = True
    try:
        yield
    finally:
        frappe.flags.dd_customer_access_write = previous


def require_manager():
    if frappe.session.user == "Guest" or not (
        frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()
    ):
        frappe.throw("Only System Managers can change client account activation.", frappe.PermissionError)


def check_access(user):
    if not user or user in ("Guest", "Administrator"):
        return
    if frappe.db.get_value("DD Customer Account", {"user": user}, "account_access") == "Deactivated":
        frappe.throw("Your account has been deactivated. Contact Diaspora Desk.", frappe.PermissionError)


def validate_auth():
    check_access(frappe.session.user)


def on_login(login_manager):
    check_access(login_manager.user)


def validate_user(doc, method=None):
    if doc.enabled:
        check_access(doc.name)


def validate_account(doc):
    if doc.get("account_access") not in (None, "", "Active", "Deactivated"):
        frappe.throw("Choose a valid account activation status.")
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and previous.user != doc.user:
        frappe.throw("A client account's linked user cannot be changed.")
    if previous:
        old_approval = previous.get("beta_access") or "Approved"
        new_approval = doc.get("beta_access") or "Approved"
        if old_approval == "Approved" and new_approval != "Approved":
            frappe.throw("Approved clients cannot be rejected or returned to Pending. Use Deactivate instead.")
        if previous.get("account_access") == "Deactivated" and new_approval != old_approval:
            frappe.throw("Reactivate the client account before changing its approval decision.")
    if frappe.flags.dd_customer_access_write:
        return
    if previous:
        if any(previous.get(key) != doc.get(key) for key in ACCESS_FIELDS):
            frappe.throw("Use the Deactivate or Reactivate action to change client account activation.")
    elif doc.get("account_access") not in (None, "", "Active") or any(
        doc.get(key) for key in ACCESS_FIELDS if key != "account_access"
    ):
        frappe.throw("New client accounts cannot contain an activation decision.")


@frappe.whitelist(methods=["POST"])
def set_account_access(account, action, reason):
    require_manager()
    if action not in ("Deactivate", "Reactivate"):
        frappe.throw("Choose Deactivate or Reactivate.")
    reason = (reason or "").strip()
    if not reason:
        frappe.throw("Enter a reason for the account activation change.")
    profile = frappe.get_doc("DD Customer Account", account, for_update=True)
    if not profile.user or profile.user in ("Administrator", "Guest", frappe.session.user):
        frappe.throw("This client account cannot be changed with this action.")
    user = frappe.get_doc("User", profile.user, for_update=True)
    # Do not turn this client-only action into a way to disable or enable staff accounts.
    if user.user_type != "Website User" or not any(row.role == "DD Customer" for row in user.roles):
        frappe.throw("Only a customer Website User can be changed with this action.")
    if any(frappe.db.get_value("Role", row.role, "desk_access") for row in user.roles):
        frappe.throw("This account has staff access. Manage it through its staff workflow.")
    inactive = profile.get("account_access") == "Deactivated"
    if action == "Reactivate" and not inactive:
        frappe.throw("Only deactivated client accounts can be reactivated. Refresh the form.")
    if action == "Deactivate" and (profile.get("beta_access") or "Approved") != "Approved":
        frappe.throw("Only approved clients can be deactivated. Review the application first.")
    if action == "Deactivate" and inactive:
        return {"status": "Deactivated"}
    with access_write():
        profile.account_access = "Deactivated" if action == "Deactivate" else "Active"
        prefix = "deactivated" if action == "Deactivate" else "reactivated"
        profile.set(prefix + "_by", frappe.session.user)
        profile.set(prefix + "_at", now_datetime())
        profile.set("deactivation_reason" if action == "Deactivate" else "reactivation_reason", reason)
        # beta_access and email_verified are deliberately never changed by these actions.
        profile.save(ignore_permissions=True)
        user.enabled = int(bool(profile.email_verified)) if action == "Reactivate" else 0
        if action == "Deactivate":
            user.api_key = None
            user.api_secret = None
            user.reset_password_key = None
        user.save(ignore_permissions=True)
        frappe.clear_cache(user=profile.user)
        if action == "Deactivate":
            from frappe.sessions import clear_sessions
            # Session deletion commits internally; keep the activation decision atomic.
            frappe.db.after_commit.add(lambda: clear_sessions(user=profile.user, force=True))
    return {"status": profile.account_access}
