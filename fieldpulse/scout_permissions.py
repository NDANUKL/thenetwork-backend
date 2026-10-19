"""Keep scout responses and evidence scoped to the currently assigned scout."""
import frappe

STAFF = {"Admin", "Supervisor", "System Manager", "Field Operations Coordinator"}


def staff(user):
    return bool(STAFF.intersection(frappe.get_roles(user)))


def record_permission(doc, user=None, ptype=None, debug=False):
    user = user or frappe.session.user
    if staff(user): return None
    scout = frappe.db.exists("Scout Profile", {"user": user})
    if not scout: return False
    if doc.doctype == "Field Task": task_name = doc.name
    elif doc.doctype == "FP Task Response": task_name = doc.task
    elif doc.doctype == "FP Question Response": task_name = frappe.db.get_value("FP Task Response", doc.task_response, "task")
    elif doc.doctype == "Field Evidence": task_name = doc.field_task
    else: return False
    if frappe.db.get_value("Field Task", task_name, "scout_profile") != scout: return False
    if doc.doctype == "FP Task Response" and doc.agent != scout: return False
    return None  # The ordinary DocPerm must still allow the operation.


def condition_for(doctype, user=None):
    user = user or frappe.session.user
    if staff(user): return ""
    scout = frappe.db.exists("Scout Profile", {"user": user})
    if not scout: return "1=0"
    value = frappe.db.escape(scout)
    task = f"SELECT name FROM `tabField Task` WHERE scout_profile={value}"
    if doctype == "Field Task": return f"`tabField Task`.scout_profile={value}"
    if doctype == "FP Task Response": return f"`tabFP Task Response`.agent={value} AND `tabFP Task Response`.task IN ({task})"
    if doctype == "FP Question Response": return f"`tabFP Question Response`.task_response IN (SELECT name FROM `tabFP Task Response` WHERE agent={value} AND task IN ({task}))"
    return f"`tabField Evidence`.scout={value} AND `tabField Evidence`.field_task IN ({task})"


def task_query(user=None): return condition_for("Field Task", user)
def response_query(user=None): return condition_for("FP Task Response", user)
def answer_query(user=None): return condition_for("FP Question Response", user)
def evidence_query(user=None): return condition_for("Field Evidence", user)
