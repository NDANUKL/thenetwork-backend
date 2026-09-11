"""Migrate legacy FP Task assignments to Field Task."""

import frappe


VALID_STATUSES = {"Assigned", "Accepted", "In Progress", "Submitted", "Approved", "Cancelled"}


def _scout_profile_for_agent(agent_name):
    return frappe.db.exists("Scout Profile", {"legacy_fp_agent": agent_name})


def execute():
    agent_to_profile = {}
    task_to_field_task = {}
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
        existing_field_task = frappe.db.exists(
            "Field Task", {"legacy_fp_task": legacy_task.name}
        )
        if existing_field_task:
            task_to_field_task[legacy_task.name] = existing_field_task
            continue
        status = legacy_task.status if legacy_task.status in VALID_STATUSES else "Assigned"
        field_task = frappe.get_doc(
            {
                "doctype": "Field Task",
                "legacy_fp_task": legacy_task.name,
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
        task_to_field_task[legacy_task.name] = field_task.name

    for response in frappe.get_all("FP Task Response", fields=["name", "task", "agent"]):
        field_task = task_to_field_task.get(response.task)
        if field_task:
            frappe.db.set_value(
                "FP Task Response", response.name, "task", field_task, update_modified=False
            )
        elif not frappe.db.exists("Field Task", response.task):
            frappe.throw(f"No Field Task exists for task response {response.name}")

        profile = agent_to_profile.get(response.agent)
        if profile:
            frappe.db.set_value("FP Task Response", response.name, "agent", profile, update_modified=False)
        elif not frappe.db.exists("Scout Profile", response.agent):
            frappe.throw(f"No Scout Profile exists for task response {response.name}")

    for sync_log in frappe.get_all("FP Sync Log", fields=["name", "agent"]):
        profile = agent_to_profile.get(sync_log.agent)
        if profile:
            frappe.db.set_value("FP Sync Log", sync_log.name, "agent", profile, update_modified=False)
        elif not frappe.db.exists("Scout Profile", sync_log.agent):
            frappe.throw(f"No Scout Profile exists for sync log {sync_log.name}")

    frappe.db.commit()
