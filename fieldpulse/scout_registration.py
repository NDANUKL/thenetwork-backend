"""Native scout registration behavior, ported from the audited production definitions."""
import json
import frappe
from fieldpulse.native_ownership import owned_event, owned_api

@frappe.whitelist()
@owned_api('DD Scout Task Team')
def task_team(**kwargs):
    # The task owner is checked server-side; clients cannot choose their identity.
    user = frappe.session.user
    if user == "Guest" or not frappe.db.get_value("User", user, "enabled"):
        frappe.throw("Sign in as the assigned scout.", frappe.PermissionError)
    if not frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": "Field Agent"}):
        frappe.throw("Sign in as the assigned scout.", frappe.PermissionError)
    scout = frappe.db.exists("Scout Profile", {"user": user})
    task_name = frappe.form_dict.get("task")
    if not scout or not task_name:
        frappe.throw("Task unavailable.", frappe.PermissionError)
    task = frappe.db.get_value("Field Task", {
        "name": task_name, "scout_profile": scout, "status": ["not in", ["Cancelled", "Rejected"]]
    }, ["name", "field_request"], as_dict=True)
    if not task:
        frappe.throw("Task unavailable.", frappe.PermissionError)
    
    teammates = []
    seen = [scout]
    if task.field_request:
        assignments = frappe.get_all("Field Task", filters={
            "field_request": task.field_request, "status": ["not in", ["Cancelled", "Rejected"]]
        }, fields=["scout_profile"], order_by="creation asc")
        for assignment in assignments:
            colleague = assignment.scout_profile
            if colleague and colleague not in seen:
                seen.append(colleague)
                profile = frappe.db.get_value("Scout Profile", colleague,
                    ["name", "user", "scout_name", "phone_number"], as_dict=True)
                if profile and profile.user and frappe.db.get_value("User", profile.user, "enabled"):
                    if frappe.db.exists("Has Role", {"parent": profile.user, "parenttype": "User", "role": "Field Agent"}):
                        teammates.append({
                            "scout_profile": profile.name,
                            "name": profile.scout_name,
                            "phone_number": profile.phone_number or "",
                        })
    frappe.response["message"] = {"task": task.name, "teammates": teammates}
    return frappe.response.pop("message", None)

@owned_event('DD Scout User Profile')
def sync_user(doc, method=None):
    from fieldpulse.scout_access import can_create_profile
    if not can_create_profile(doc.name):
        return
    is_scout = False
    for role in doc.get("roles") or []:
        if role.role == "Field Agent":
            is_scout = True
    
    if is_scout and doc.name not in ["Guest", "Administrator"]:
        if not frappe.db.exists("Scout Profile", {"user": doc.name}):
            agent_name = frappe.db.exists("FP Agent", {"user": doc.name})
            existing = None
            if agent_name:
                existing = frappe.db.exists("Scout Profile", {"legacy_fp_agent": agent_name})
            if existing:
                profile = frappe.get_doc("Scout Profile", existing)
                if not profile.user:
                    profile.user = doc.name
                    profile.save(ignore_permissions=True)
            else:
                values = {
                    "doctype": "Scout Profile",
                    "user": doc.name,
                    "scout_name": doc.full_name or doc.first_name or doc.name,
                    "phone_number": doc.mobile_no or doc.phone or "",
                    "availability_status": "Available",
                }
                if agent_name:
                    agent = frappe.get_doc("FP Agent", agent_name)
                    values["legacy_fp_agent"] = agent.name
                    values["phone_number"] = agent.phone or values["phone_number"]
                frappe.get_doc(values).insert(ignore_permissions=True)

@owned_event('DD Scout Agent Profile')
def sync_agent(doc, method=None):
    # Mobile registration inserts FP Agent after User. Complete the new profile's
    # legacy link and contact information without changing operational settings.
    if doc.user:
        from fieldpulse.scout_access import can_create_profile
        if not (can_create_profile(doc.user) or frappe.db.exists("Scout Profile", {"user": doc.user})):
            return
        is_scout = frappe.db.exists("Has Role", {
            "parent": doc.user, "parenttype": "User", "role": "Field Agent"
        })
        if is_scout:
            profile_name = frappe.db.exists("Scout Profile", {"user": doc.user})
            if not profile_name:
                profile_name = frappe.db.exists("Scout Profile", {"legacy_fp_agent": doc.name})
            if profile_name:
                profile = frappe.get_doc("Scout Profile", profile_name)
                changed = False
                if not profile.user:
                    profile.user = doc.user
                    changed = True
                if not profile.legacy_fp_agent:
                    profile.legacy_fp_agent = doc.name
                    changed = True
                if not profile.phone_number and doc.phone:
                    profile.phone_number = doc.phone
                    changed = True
                if changed:
                    profile.save(ignore_permissions=True)
            else:
                frappe.get_doc({
                    "doctype": "Scout Profile",
                    "user": doc.user,
                    "scout_name": doc.full_name or doc.user,
                    "phone_number": doc.phone or "",
                    "legacy_fp_agent": doc.name,
                    "availability_status": "Available",
                }).insert(ignore_permissions=True)
