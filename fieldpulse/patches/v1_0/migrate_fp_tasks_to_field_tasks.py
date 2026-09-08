"""Migrate legacy FP Task assignments to Field Task."""

import frappe


VALID_STATUSES = {"Assigned", "Accepted", "In Progress", "Submitted", "Approved", "Cancelled"}


def _scout_profile_for_agent(agent_name):
    user = frappe.db.get_value("FP Agent", agent_name, "user")
    if user:
        return frappe.db.exists("Scout Profile", {"user": user})
    full_name = frappe.db.get_value("FP Agent", agent_name, "full_name")
    return frappe.db.exists("Scout Profile", {"scout_name": full_name})


def execute():
    agent_to_profile = {}
    for agent in frappe.get_all("FP Agent", fields=["name"]):
        profile = _scout_profile_for_agent(agent.name)
        if not profile:
            frappe.throw(f"No Scout Profile exists for legacy FP Agent {agent.name}")
        agent_to_profile[agent.name] = profile

    for legacy_task in frappe.get_all(
        "FP Task",
        fields=[
            "name", "agent", "location", "questionnaire", "questionnaire_version",
            "status", "due_at", "assigned_at", "submitted_at",
        ],
    ):
        if frappe.db.exists("Field Task", legacy_task.name):
            continue
        status = legacy_task.status if legacy_task.status in VALID_STATUSES else "Assigned"
        field_task = frappe.get_doc(
            {
                "doctype": "Field Task",
                "name": legacy_task.name,
                "scout_profile": agent_to_profile[legacy_task.agent],
                "location": legacy_task.location,
                "questionnaire": legacy_task.questionnaire,
                "questionnaire_version": legacy_task.questionnaire_version,
                "status": status,
                "due_at": legacy_task.due_at,
                "assigned_at": legacy_task.assigned_at,
                "submitted_at": legacy_task.submitted_at,
            }
        ).insert(ignore_permissions=True)
        if field_task.name != legacy_task.name:
            frappe.throw(
                f"Field Task naming did not preserve legacy FP Task name {legacy_task.name}"
            )

    for response in frappe.get_all("FP Task Response", fields=["name", "agent"]):
        profile = agent_to_profile.get(response.agent)
        if not profile:
            frappe.throw(f"No Scout Profile exists for task response {response.name}")
        frappe.db.set_value("FP Task Response", response.name, "agent", profile, update_modified=False)

    for sync_log in frappe.get_all("FP Sync Log", fields=["name", "agent"]):
        profile = agent_to_profile.get(sync_log.agent)
        if not profile:
            frappe.throw(f"No Scout Profile exists for sync log {sync_log.name}")
        frappe.db.set_value("FP Sync Log", sync_log.name, "agent", profile, update_modified=False)

    frappe.db.commit()
