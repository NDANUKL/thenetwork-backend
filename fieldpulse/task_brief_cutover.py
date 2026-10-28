"""Cutover inventory and the explicitly authorized production cancellation."""
import frappe

AUTHORIZED_SITE = 'thenetwork.frappe.cloud'
AUTHORIZED_TASKS = (
    '1ejqkmfbt9', '4moelkftfh', '5js5dk5daj', '7ga0nmcpu6',
    '8eeesos3ea', '8uujf5mp3q', '967jnmdhdu', '9g7pmoqt7s',
    'bgamlcp1ph', 'bk4uo1cula', 'cksr2tu3jk', 'dql3dbvfsl',
)
CANCELLATION_LOG = 'fieldpulse.task_brief_cutover.cancel_authorized_legacy_2026_10_28'


def cancel_authorized_legacy_tasks():
    """One-time owner-approved cancellation, before new schema is available.

    Use existing columns directly: saving Field Task through the new controller
    before model sync would require fields not yet installed. No data is deleted.
    The migration transaction owns the commit; an error rolls back this unit.
    """
    if frappe.local.site != AUTHORIZED_SITE or frappe.db.exists('Patch Log', {'patch': CANCELLATION_LOG}):
        return
    frappe.db.savepoint('authorized_brief_cutover')
    try:
        placeholders = ', '.join(['%s'] * len(AUTHORIZED_TASKS))
        frappe.db.sql(f'SELECT name FROM `tabField Task` WHERE name IN ({placeholders}) ORDER BY name FOR UPDATE', AUTHORIZED_TASKS)
        tasks = open_legacy_tasks()
        if any(row.name not in AUTHORIZED_TASKS for row in tasks):
            # Do not partially execute an approval if the production inventory changed.
            return
        projects, scouts = set(), set()
        for task in tasks:
            previous_status = task.status
            revisits = []
            if frappe.db.exists('DocType', 'DD Revisit Request'):
                revisits = frappe.get_all('DD Revisit Request', filters={
                    'task': task.name, 'status': ['in', ['Awaiting authorization', 'Authorized']]}, pluck='name')
                for name in revisits:
                    frappe.db.set_value('DD Revisit Request', name, 'status', 'Cancelled')
            frappe.db.set_value('Field Task', task.name, 'status', 'Cancelled')
            frappe.get_doc(dict(doctype='Comment', comment_type='Info',
                reference_doctype='Field Task', reference_name=task.name,
                content='Owner-authorized Task Brief cutover cancellation (28 October 2026). '
                    f'Previous status: {previous_status}. Submissions, evidence and assignment history retained. '
                    'Pending revisit authorizations cancelled: ' + (', '.join(revisits) or 'none')
            )).insert(ignore_permissions=True)
            if task.field_request: projects.add(task.field_request)
            if task.scout_profile: scouts.add(task.scout_profile)
        for project in sorted(projects):
            if not frappe.db.exists('Field Task', {'field_request': project, 'status': ['!=', 'Cancelled']}):
                status = frappe.db.get_value('Field Request', project, 'status')
                if status and status not in ('Completed', 'Cancelled'):
                    frappe.db.set_value('Field Request', project, 'status', 'Awaiting Assignment')
        if scouts:
            from fieldpulse.fieldpulse.doctype.scout_profile.scout_profile import recalculate_workload_and_availability
            for scout in sorted(scouts): recalculate_workload_and_availability(scout)
        frappe.get_doc(dict(doctype='Patch Log', patch=CANCELLATION_LOG)).insert(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point='authorized_brief_cutover')
        raise


def cancelled_legacy_tasks(scout, since=None):
    """Send explicit terminal states, so devices do not infer withdrawal."""
    if frappe.local.site != AUTHORIZED_SITE:
        return []
    filters = {'name': ['in', list(AUTHORIZED_TASKS)], 'scout_profile': scout, 'status': 'Cancelled'}
    if since: filters['modified'] = ['>', since]
    return frappe.get_all('Field Task', filters=filters, fields=['*'])


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
    cancel_authorized_legacy_tasks()
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
