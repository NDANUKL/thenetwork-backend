"""Durable rework email delivery; a failed sender never loses the rework request."""
from datetime import timedelta
from hashlib import sha256
from html import escape
import json
import requests
import frappe

DOCTYPE = 'DD Scout Notification'


def queue_rework(task, response, kind, codes, notes):
    user = frappe.db.get_value('Scout Profile', task.scout_profile, 'user')
    if not user: frappe.throw('The assigned scout needs a linked user to receive rework')
    key = sha256(('rework:' + response.name).encode()).hexdigest()
    if frappe.db.exists(DOCTYPE, key): return key
    title = f'Rework required: {kind} — {task.get("task_number") or task.name}'
    body = f'{kind}\nQuestions: {", ".join(codes)}\n\n{notes}\n\nOpen the scout app and sync to receive your response revision.'
    if task.get('replaces_task'):
        title = 'Site revisit assigned - ' + (task.get('task_number') or task.name)
        body = f'You have a new site revisit assignment. Record your own arrival, answers and evidence.\nQuestions requiring attention: {", ".join(codes)}\n\n{notes}\n\nOpen the scout app and sync to receive this assignment.'
    # Desk inbox, in addition to the persistent banner supplied through mobile sync.
    frappe.get_doc(dict(doctype='Notification Log', for_user=user, from_user=frappe.session.user,
        type='Alert', subject=title, email_content=escape(body).replace('\n', '<br>'),
        document_type='Field Task', document_name=task.name)).insert(ignore_permissions=True)
    frappe.get_doc(dict(doctype=DOCTYPE, event_key=key, task=task.name, source_response=response.name,
        scout=task.scout_profile, recipient=user, subject=title, message=body,
        status='Pending', attempts=0, next_attempt_at=frappe.utils.now_datetime())).insert(ignore_permissions=True)
    try: frappe.enqueue('fieldpulse.scout_notifications.send', notification=key, enqueue_after_commit=True)
    except Exception: pass  # The scheduler retries the durable row.
    return key


def send(notification):
    from fieldpulse.customer_notifications import delivery_config
    frappe.db.sql('SELECT name FROM `tabDD Scout Notification` WHERE name=%s FOR UPDATE', [notification])
    record = frappe.get_doc(DOCTYPE, notification)
    now = frappe.utils.now_datetime()
    if record.status != 'Pending' or (record.next_attempt_at and frappe.utils.get_datetime(record.next_attempt_at) > now): return
    task = frappe.get_doc('Field Task', record.task)
    user = frappe.db.get_value('Scout Profile', task.scout_profile, 'user')
    if task.scout_profile != record.scout or user != record.recipient or not frappe.db.get_value('User', user, 'enabled') or task.status in ('Approved', 'Cancelled'):
        frappe.db.set_value(DOCTYPE, record.name, 'status', 'Skipped')
        return
    if record.first_attempt_at and now - frappe.utils.get_datetime(record.first_attempt_at) >= timedelta(hours=23):
        frappe.db.set_value(DOCTYPE, record.name, {'status': 'Needs review', 'last_error': 'Delivery outcome needs operator review; idempotency retry window expired.'})
        return
    attempts = int(record.attempts or 0) + 1
    try:
        key, sender, _ = delivery_config()
        email = frappe.db.get_value('User', user, 'email') or user
        payload = json.loads(record.payload) if record.get('payload') else dict(
            **{'from': sender}, to=[email], subject=record.subject,
            html='<p>' + escape(record.message).replace('\n', '<br>') + '</p>', text=record.message)
        frappe.db.set_value(DOCTYPE, record.name, dict(payload=json.dumps(payload),
            attempts=attempts, first_attempt_at=record.first_attempt_at or now))
        # Persist the stable provider payload before network IO, then regain the lock.
        frappe.db.commit()
        frappe.db.sql('SELECT name FROM `tabDD Scout Notification` WHERE name=%s FOR UPDATE', [notification])
        record.reload()
        task.reload()
        if record.status != 'Pending': return
        if task.scout_profile != record.scout or task.status in ('Approved', 'Cancelled') or frappe.db.get_value('Scout Profile', task.scout_profile, 'user') != record.recipient:
            frappe.db.set_value(DOCTYPE, record.name, 'status', 'Skipped')
            return
        result = requests.post('https://api.resend.com/emails', timeout=20,
            headers={'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'dd-scout-' + record.name}, json=payload)
        if not result.ok or not result.json().get('id'): raise ValueError('Email provider did not accept the rework notification')
        frappe.db.set_value(DOCTYPE, record.name, dict(status='Sent', sent_at=frappe.utils.now_datetime(), last_error=''))
    except Exception:
        frappe.db.set_value(DOCTYPE, record.name, dict(attempts=attempts,
            next_attempt_at=now + timedelta(minutes=min(60, 2 ** min(attempts, 6))),
            last_error='Rework email delivery failed; check the shared sender settings.'))


def retry_pending():
    for name in frappe.get_all(DOCTYPE, filters={'status': 'Pending', 'next_attempt_at': ['<=', frappe.utils.now_datetime()]}, pluck='name', limit=100):
        frappe.enqueue('fieldpulse.scout_notifications.send', notification=name)
