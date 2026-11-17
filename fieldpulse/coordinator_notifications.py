"""Queue client and scout application alerts through Frappe's Email Queue."""
import hashlib
import json
import frappe
from frappe.utils import get_url_to_form


def application_received(doc):
    _notify(doc, doctype='Scout Application', title='New scout application',
        subject='New scout application', name=doc.name,
        summary='A new scout application is ready for review.',
        person=doc.full_name or 'New applicant', location=doc.county or 'County unconfirmed',
        label='Review application')


def client_application_received(doc):
    """Persist and enqueue an alert only for newly registered Pending clients."""
    if doc.get('beta_access') != 'Pending':
        return
    identity = 'dd-client-application:' + doc.name
    key = hashlib.sha256(identity.encode('utf-8')).hexdigest()
    record = frappe.get_doc({
        'doctype': 'DD Coordinator Alert', 'event_key': key,
        'reference_doctype': 'DD Customer Account', 'reference_name': doc.name,
        'status': 'Pending',
    })
    try:
        record.insert(ignore_permissions=True)
    except frappe.DuplicateEntryError:
        record = frappe.get_doc('DD Coordinator Alert', key)
        if record.status != 'Pending':
            return
    frappe.enqueue('fieldpulse.coordinator_notifications.send_client_application',
                   alert=key, enqueue_after_commit=True)


def _notify(doc, *, doctype, title, subject, name, summary, person, location, label):
    users = frappe.get_all('Has Role', filters={
        'role': 'Field Operations Coordinator', 'parenttype': 'User'
    }, pluck='parent')
    recipients = frappe.get_all('User', filters={
        'name': ['in', users], 'enabled': 1, 'user_type': 'System User'
    }, pluck='email') if users else []
    recipients = sorted({email for email in recipients if email})
    if not recipients:
        frappe.log_error(title='Coordinator application notification',
                         message='No enabled coordinator email recipient is configured.')
        return
    from fieldpulse.email_branding import render_email
    html = render_email(title=title, eyebrow='COORDINATOR UPDATE',
        body=f"{frappe.utils.escape_html(summary)}<br><strong>{frappe.utils.escape_html(person)}</strong><br>{frappe.utils.escape_html(location)}",
        origin=frappe.utils.get_url(), link=get_url_to_form(doctype, name),
        label=label, note='Sign in to Frappe to review this application. You received this email because you are a Field Operations Coordinator.',
        body_is_html=True)
    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=html,
        reference_doctype=doctype, reference_name=name,
        delayed=True,
    )


def send_client_application(alert):
    """Deliver a persisted Pending client alert; leave failed attempts retryable."""
    try:
        record = frappe.get_doc('DD Coordinator Alert', alert, for_update=True)
    except frappe.DoesNotExistError:
        return
    if record.status != 'Pending':
        return
    now = frappe.utils.now_datetime()
    if record.get('next_attempt_at') and frappe.utils.get_datetime(record.next_attempt_at) > now:
        return
    record.db_set('status', 'Sending', update_modified=False)
    if not frappe.db.exists('DD Customer Account', {
            'name': record.reference_name, 'beta_access': 'Pending'}):
        record.db_set('status', 'Skipped', update_modified=False)
        return
    try:
        account = frappe.get_doc('DD Customer Account', record.reference_name)
        user = frappe.get_doc('User', account.user)
        _notify(account, doctype='DD Customer Account', title='New client waiting for approval',
            subject='New client waiting for approval', name=account.name,
            summary='A new client account is ready for review.',
            person=user.full_name or account.user, location=account.user,
            label='Review client account')
        record.db_set('status', 'Sent', update_modified=False)
        record.db_set('last_error', '', update_modified=False)
        record.db_set('next_attempt_at', None, update_modified=False)
    except Exception:
        record.db_set('attempts', (record.attempts or 0) + 1, update_modified=False)
        record.db_set('last_error', 'Coordinator alert delivery failed', update_modified=False)
        record.db_set('next_attempt_at', frappe.utils.add_to_date(now, minutes=5), update_modified=False)
        frappe.log_error(title='Client approval alert failed',
                         message=f'Alert {record.name} could not be queued; it will be retried.')
        record.db_set('status', 'Pending', update_modified=False)


def retry_client_applications():
    """Re-enqueue Pending alerts left behind by worker/queue interruptions."""
    rows = frappe.get_all('DD Coordinator Alert', filters={
        'status': 'Pending', 'next_attempt_at': ['<=', frappe.utils.now_datetime()]},
                          pluck='name', limit_page_length=100)
    for alert in rows:
        frappe.enqueue('fieldpulse.coordinator_notifications.send_client_application',
                       alert=alert, enqueue_after_commit=True)
