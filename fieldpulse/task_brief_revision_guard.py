"""Serialize brief changes with dispatch and protect possible offline work."""
import frappe


def lock_project(project):
    frappe.db.sql('SELECT name FROM `tabField Request` WHERE name=%s FOR UPDATE', [project])


def require_undispatched_project(project):
    lock_project(project)
    # Do not use status/started_at as proof that a phone has no offline work.
    # Cancelled allocations also retain their pins and possible unsent evidence.
    if frappe.db.get_value('Field Task', {
        'field_request': project, 'task_brief_version': ['is', 'set'],
    }, 'name', for_update=True):
        frappe.throw('This project already has an assigned Task Brief. New versions and changes '
                     'to the approved brief are locked because a scout may have started offline. '
                     'Keep the assigned brief and use submission review for follow-up work.')
