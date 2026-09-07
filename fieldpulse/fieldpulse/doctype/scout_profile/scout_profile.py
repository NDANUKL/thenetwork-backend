import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime


ACTIVE_TASK_STATUSES = ("Assigned", "Accepted", "In Progress")


class ScoutProfile(Document):
    """Operational profile for a field scout."""

    pass


def refresh_activity_statuses():
    """Persist active/inactive state so Desk list views can filter it."""
    cutoff = add_days(now_datetime(), -30)
    frappe.db.sql(
        """
        UPDATE `tabScout Profile`
        SET activity_status = CASE
            WHEN last_app_activity IS NOT NULL AND last_app_activity >= %(cutoff)s THEN 'Active'
            ELSE 'Inactive'
        END
        """,
        {"cutoff": cutoff},
    )


def recalculate_workload_and_availability(scout_profile):
    """Refresh counters and automatic availability after a Field Task change."""
    if not frappe.db.exists("DocType", "Field Task"):
        return

    active_task_count = frappe.db.count(
        "Field Task",
        {"scout_profile": scout_profile, "status": ["in", ACTIVE_TASK_STATUSES]},
    )
    completed_task_count = frappe.db.count(
        "Field Task",
        {"scout_profile": scout_profile, "status": "Completed"},
    )
    profile = frappe.get_doc("Scout Profile", scout_profile)
    updates = {
        "active_task_count": active_task_count,
        "completed_task_count": completed_task_count,
    }
    if profile.availability_status != "On Leave":
        updates["availability_status"] = "Busy" if active_task_count else "Available"

    frappe.db.set_value("Scout Profile", scout_profile, updates, update_modified=False)
