"""Scout-owned data deletion requests. No field evidence is deleted by this API."""
import hashlib
import secrets
from urllib.parse import urlencode, urlsplit

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url, validate_email_address
from frappe.utils.password import check_password


def _is_scout(user):
    return bool(frappe.db.exists('Scout Profile', {'user': user}) or frappe.db.exists('Scout Application', {'user': user}))


def _user():
    user = frappe.session.user
    if user == 'Guest' or not _is_scout(user):
        frappe.throw('Sign in to your scout account.', frappe.PermissionError)
    return user


def _payload(doc):
    return {'reference': doc.name, 'status': doc.status, 'reply': doc.get('public_reply') or '', 'requested_at': str(doc.creation)}


def _request(user, reason):
    reason = str(reason or '').strip()
    if len(reason) > 1000:
        frappe.throw('Reason must be at most 1000 characters.')
    # Serialize retries and the email/app paths without disclosing another account.
    frappe.db.sql('SELECT name FROM `tabUser` WHERE name=%s FOR UPDATE', (user,))
    existing = frappe.db.get_value('Scout Data Request', {'user': user, 'status': ['in', ['Open', 'Under review']]}, 'name')
    if existing:
        return _payload(frappe.get_doc('Scout Data Request', existing))
    previous = frappe.flags.scout_data_request
    frappe.flags.scout_data_request = True
    try:
        doc = frappe.get_doc({'doctype': 'Scout Data Request', 'user': user, 'reason': reason, 'status': 'Open'}).insert(ignore_permissions=True)
    finally:
        frappe.flags.scout_data_request = previous
    return _payload(doc)


@frappe.whitelist(methods=['GET'])
def deletion_status():
    user = _user()
    rows = frappe.get_all('Scout Data Request', filters={'user': user}, fields=['name'], order_by='creation desc', limit_page_length=1)
    return {'request': _payload(frappe.get_doc('Scout Data Request', rows[0].name)) if rows else None}


@frappe.whitelist(methods=['POST'])
@rate_limit(limit=5, seconds=3600)
def request_deletion(password, reason=''):
    user = _user()
    if not isinstance(password, str) or not password or len(password) > 512:
        frappe.throw('Confirm your password to request account deletion.')
    check_password(user, password)
    return _request(user, reason)


@frappe.whitelist(allow_guest=True, methods=['POST'])
@rate_limit(limit=10, seconds=3600)
@rate_limit(key='email', limit=3, seconds=3600)
def email_deletion_link(email, reason=''):
    # Identical response for unknown, inactive, pending and registered emails.
    reply = {'message': 'If this email belongs to a scout account, a confirmation link will be sent. Check your inbox.'}
    try:
        user = validate_email_address(str(email or '').strip().lower(), throw=True)
    except Exception:
        return reply
    site = str(frappe.conf.get('dd_scout_public_url') or frappe.conf.get('host_name') or '').rstrip('/')
    parts = urlsplit(site)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/'):
        frappe.throw('Secure account recovery is unavailable. Contact support.')
    if len(str(reason or '')) > 1000 or not _is_scout(user):
        return reply
    token = secrets.token_urlsafe(32)
    key = 'scout-deletion:' + hashlib.sha256(token.encode()).hexdigest()
    frappe.cache().set_value(key, {'user': user, 'reason': str(reason or '').strip()}, expires_in_sec=1800)
    link = site + '/scout-data-deletion#' + urlencode({'token': token})
    frappe.sendmail(recipients=[user], subject='Confirm your Ground Scouts account deletion request',
                    message='Someone requested deletion of your Ground Scouts account. If this was you, open the link and confirm within 30 minutes. Opening the link alone does not submit the request. Ignore this email if you did not request it.<br><a href="' + link + '">Review and confirm request</a>')
    return reply


@frappe.whitelist(allow_guest=True, methods=['POST'])
@rate_limit(limit=10, seconds=3600)
def confirm_email_deletion(token):
    if not isinstance(token, str) or not 20 <= len(token) <= 100:
        frappe.throw('This confirmation link is invalid or expired. Request a new link.')
    key = 'scout-deletion:' + hashlib.sha256(token.encode()).hexdigest()
    value = frappe.cache().get_value(key)
    if not value or not _is_scout(value.get('user')):
        frappe.throw('This confirmation link is invalid or expired. Request a new link.')
    result = _request(value['user'], value.get('reason', ''))
    frappe.db.commit()
    frappe.cache().delete_value(key)
    return result
