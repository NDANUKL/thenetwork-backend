"""Durable assignment, withdrawal, authorization and rework email delivery."""
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
    title = f'Correction requested: {task.get("task_number") or task.name}'
    body = f'Your coordinator requested a full resubmission. Review the instructions below, update any answers that need correction, and add the requested evidence. Your previous answers and evidence are retained.\n\nChecks: {", ".join(codes)}\n\nCoordinator instructions:\n{notes}\n\nOpen Ground Scouts and sync to continue.'
    if task.get('replaces_task'):
        title = 'Site revisit assigned - ' + (task.get('task_number') or task.name)
        body = f'You have a new site revisit assignment. Record your own arrival, answers and evidence.\nQuestions requiring attention: {", ".join(codes)}\n\n{notes}\n\nOpen the scout app and sync to receive this assignment.'
    # Desk inbox, in addition to the persistent banner supplied through mobile sync.
    frappe.get_doc(dict(doctype='Notification Log', for_user=user, from_user=frappe.session.user,
        type='Alert', subject=title, email_content=escape(body).replace('\n', '<br>'),
        document_type='Field Task', document_name=task.name)).insert(ignore_permissions=True)
    frappe.get_doc(dict(doctype=DOCTYPE, event_key=key, task=task.name, source_response=response.name,
        scout=task.scout_profile, recipient=user, subject=title, message=body, event_kind='Rework',
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
    if not delivery_current(record, task):
        frappe.db.set_value(DOCTYPE, record.name, 'status', 'Skipped')
        return
    if record.first_attempt_at and now - frappe.utils.get_datetime(record.first_attempt_at) >= timedelta(hours=23):
        frappe.db.set_value(DOCTYPE, record.name, {'status': 'Needs review', 'last_error': 'Delivery outcome needs operator review; idempotency retry window expired.'})
        return
    attempts = int(record.attempts or 0) + 1
    try:
        key, sender, _ = delivery_config()
        email = frappe.db.get_value('User', record.recipient, 'email') or record.recipient
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
        if not delivery_current(record, task):
            frappe.db.set_value(DOCTYPE, record.name, 'status', 'Skipped')
            return
        result = requests.post('https://api.resend.com/emails', timeout=20,
            headers={'Authorization': 'Bearer ' + key, 'Idempotency-Key': 'dd-scout-' + record.name}, json=payload)
        if not result.ok or not result.json().get('id'): raise ValueError('Email provider did not accept the scout notification')
        frappe.db.set_value(DOCTYPE, record.name, dict(status='Sent', sent_at=frappe.utils.now_datetime(), last_error=''))
    except Exception:
        frappe.db.set_value(DOCTYPE, record.name, dict(attempts=attempts,
            next_attempt_at=now + timedelta(minutes=min(60, 2 ** min(attempts, 6))),
            last_error='Scout email delivery failed; check the shared sender settings.'))


def retry_pending():
    for name in frappe.get_all(DOCTYPE, filters={'status': 'Pending', 'next_attempt_at': ['<=', frappe.utils.now_datetime()]}, pluck='name', limit=100):
        frappe.enqueue('fieldpulse.scout_notifications.send', notification=name)


def delivery_current(record, task):
    user = frappe.db.get_value('Scout Profile', record.scout, 'user')
    if user != record.recipient or not frappe.db.get_value('User', user, 'enabled'):
        return False
    kind = record.get('event_kind') or 'Rework'
    if kind == 'Withdrawal':
        # An old assignee must receive withdrawal even after ownership changes.
        return task.scout_profile != record.scout or task.status == 'Cancelled'
    if task.scout_profile != record.scout or task.status in ('Approved', 'Cancelled'):
        return False
    if kind == 'Authorization':
        return task.status == record.get('assignment_status')
    if kind == 'Assignment':
        return task.status in ('Assigned', 'Accepted', 'In Progress')
    return True


def queue_task_event(task, scout, kind):
    user = frappe.db.get_value('Scout Profile', scout, 'user') if scout else None
    if not user or not frappe.db.get_value('User', user, 'enabled'):
        return None
    revision = str(task.get('modified') or task.get('creation') or '')
    key = sha256(json.dumps([task.name, scout, kind, task.status, revision]).encode()).hexdigest()
    if frappe.db.exists(DOCTYPE, key):
        return key
    reference = task.get('task_number') or task.name
    rejected = kind == 'Withdrawal' and task.get('submission_review_status') == 'Reject'
    title = 'Assignment rejected' if rejected else {'Assignment':'New assignment', 'Withdrawal':'Assignment withdrawn', 'Authorization':'Revisit authorization updated'}[kind]
    instruction = 'Open Ground Scouts and sync to read the current assignment.'
    if rejected:
        reason = (task.get('submission_review_reasons') or '').strip()
        if reason.startswith('Rejected:'):
            reason = reason[len('Rejected:'):].strip()
        instruction = f'Your assignment was rejected. Reason: {reason}. This assignment is closed. Open Ground Scouts and sync to review the decision.'
    elif kind == 'Withdrawal':
        instruction = 'Stop work on this assignment. Keep unsent work on your device and contact your coordinator. Open Ground Scouts and sync.'
    elif task.status == 'Awaiting authorization':
        instruction = 'Do not revisit yet. Await coordinator authorization. Open Ground Scouts and sync for the current status.'
    # No client names, findings, payment details or review notes in these alerts.
    message = f'{title}: {reference}. {instruction}'
    frappe.get_doc(dict(doctype=DOCTYPE,event_key=key,task=task.name,scout=scout,recipient=user,
        event_kind=kind,assignment_status=task.status,subject=title,message=message,
        status='Pending',attempts=0,next_attempt_at=frappe.utils.now_datetime())).insert(ignore_permissions=True)
    frappe.get_doc(dict(doctype='Notification Log',for_user=user,from_user=frappe.session.user,
        type='Alert',subject=title,email_content=escape(message),document_type='Field Task',
        document_name=task.name)).insert(ignore_permissions=True)
    try:
        frappe.enqueue('fieldpulse.scout_notifications.send',notification=key,enqueue_after_commit=True)
    except Exception:
        pass  # Durable pending records are retried by the existing scheduler.
    return key


def capture_task(task, method=None):
    if getattr(frappe.flags,'in_migrate',False) or getattr(frappe.flags,'in_install',False):
        return
    previous = task.get_doc_before_save()
    old_scout = previous.get('scout_profile') if previous else None
    changed_owner = bool(previous and old_scout != task.scout_profile)
    if old_scout and (changed_owner or task.status == 'Cancelled' and previous.status != 'Cancelled'):
        queue_task_event(task,old_scout,'Withdrawal')
    if task.scout_profile and task.status in ('Assigned','Accepted','In Progress'):
        if not previous or changed_owner:
            queue_task_event(task,task.scout_profile,'Assignment')
        elif previous.status == 'Awaiting authorization':
            queue_task_event(task,task.scout_profile,'Authorization')
    elif task.scout_profile and task.status == 'Awaiting authorization' and (not previous or changed_owner or previous.status != task.status):
        queue_task_event(task,task.scout_profile,'Authorization')
