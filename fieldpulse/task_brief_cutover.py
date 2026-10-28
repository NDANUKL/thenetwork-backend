"""Read-only rollout inventory. Never convert or cancel fieldwork implicitly."""
import frappe


def open_legacy_tasks(scout=None):
    filters = {'status': ['not in', ['Approved', 'Cancelled']]}
    if scout:
        filters['scout_profile'] = scout
    if frappe.db.has_column('Field Task', 'task_brief_version'):
        filters['task_brief_version'] = ['is', 'not set']
    return frappe.get_all('Field Task', filters=filters,
        fields=['name', 'field_request', 'scout_profile', 'status'], order_by='name')


def assert_ready():
    if not frappe.db.exists('DocType', 'Field Task'):
        return
    tasks = open_legacy_tasks()
    if tasks:
        frappe.throw('Task Brief cutover blocked: reconcile open legacy assignments and unsent device work before migration. '
            'Run bench execute fieldpulse.task_brief_cutover.inventory. Open tasks: ' + ', '.join(row.name for row in tasks[:20]))


def inventory():
    """Bench-only inventory; saved mobile work must also be reconciled per device."""
    tasks = open_legacy_tasks()
    return {'ready': not tasks, 'open_legacy_tasks': tasks,
            'device_work_verified': False,
            'next_step': 'Recover unsent device work, then explicitly close or rebrief/reassign each allocation. Never infer checks from categories.'}
