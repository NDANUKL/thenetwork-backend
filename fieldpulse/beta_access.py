"""Customer access policy. Blank statuses preserve accounts created before beta."""
import frappe

INVITE_ONLY = "Invite only"

def registration_access():
    value = frappe.db.get_single_value("DD Access Settings", "registration_access")
    return "Open to everyone" if value == "Open to everyone" else INVITE_ONLY

def access_status(account):
    if account.get("account_access") == "Deactivated":
        return "Deactivated"
    status = account.get("beta_access") or "Approved"
    if status == "Pending" and registration_access() == "Open to everyone":
        return "Approved"
    return status

def require_access(account):
    if isinstance(account, str):
        account = frappe.get_doc("DD Customer Account", account)
    status = access_status(account)
    if status != "Approved":
        frappe.throw("Beta access has not been approved", frappe.PermissionError)

@frappe.whitelist(allow_guest=True, methods=["GET"])
def policy():
    return {"registration_access": registration_access()}
