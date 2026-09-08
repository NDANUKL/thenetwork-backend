"""Reusable performance queries for Field Task operations."""

import frappe


def performance_metrics(scout_profile=None):
    """Return response, completion, timeliness, and rework metrics by scout."""
    filters = ["ft.status = 'Approved'"]
    values = {}
    if scout_profile:
        filters.append("ft.scout_profile = %(scout_profile)s")
        values["scout_profile"] = scout_profile

    return frappe.db.sql(
        f"""
        SELECT
            ft.scout_profile,
            AVG(CASE WHEN ft.accepted_at IS NOT NULL
                THEN TIMESTAMPDIFF(SECOND, ft.assigned_at, ft.accepted_at) END) AS avg_response_seconds,
            AVG(CASE WHEN ft.completed_at IS NOT NULL
                THEN TIMESTAMPDIFF(SECOND, ft.assigned_at, ft.completed_at) END) AS avg_turnaround_seconds,
            AVG(CASE WHEN ft.due_at IS NOT NULL AND ft.completed_at <= ft.due_at
                THEN 1 ELSE 0 END) AS on_time_completion_rate,
            AVG(CASE WHEN ft.rework_count > 0 THEN 1 ELSE 0 END) AS rework_rate,
            COUNT(*) AS completed_task_count
        FROM `tabField Task` ft
        WHERE {' AND '.join(filters)}
        GROUP BY ft.scout_profile
        """,
        values,
        as_dict=True,
    )


def performance_by_task_type(scout_profile=None):
    """Return approved-task performance grouped by Field Request request type."""
    filters = ["ft.status = 'Approved'"]
    values = {}
    if scout_profile:
        filters.append("ft.scout_profile = %(scout_profile)s")
        values["scout_profile"] = scout_profile

    return frappe.db.sql(
        f"""
        SELECT
            ft.scout_profile,
            fr.request_type,
            COUNT(*) AS completed_task_count,
            AVG(CASE WHEN ft.due_at IS NOT NULL AND ft.completed_at <= ft.due_at
                THEN 1 ELSE 0 END) AS on_time_completion_rate,
            AVG(CASE WHEN ft.completed_at IS NOT NULL
                THEN TIMESTAMPDIFF(SECOND, ft.assigned_at, ft.completed_at) END) AS avg_turnaround_seconds
        FROM `tabField Task` ft
        LEFT JOIN `tabField Request` fr ON fr.name = ft.field_request
        WHERE {' AND '.join(filters)}
        GROUP BY ft.scout_profile, fr.request_type
        """,
        values,
        as_dict=True,
    )


def similar_tasks_completed(scout_profile, request_type):
    """Count approved tasks of a particular request type for one scout."""
    field_request_names = frappe.get_all(
        "Field Request", filters={"request_type": request_type}, pluck="name"
    )
    if not field_request_names:
        return 0
    return frappe.db.count(
        "Field Task",
        {
            "scout_profile": scout_profile,
            "status": "Approved",
            "field_request": ["in", field_request_names],
        },
    )


def current_workload(scout_profile):
    """Return the materialized active workload maintained on Scout Profile."""
    return frappe.db.get_value("Scout Profile", scout_profile, "active_task_count") or 0
