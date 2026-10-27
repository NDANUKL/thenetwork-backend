"""Scout session limits and verified two-factor login boundaries."""
import frappe
from frappe.utils import get_datetime, now_datetime

ABSOLUTE_SESSION_SECONDS = 7 * 24 * 60 * 60


def is_scout(user):
    return user not in (None, 'Guest', 'Administrator') and bool(
        frappe.db.exists('Scout Profile', {'user': user}))


def mfa_required(user):
    if not is_scout(user):
        return False
    from frappe.twofactor import should_run_2fa
    return bool(should_run_2fa(user))


def require_verified_login(user):
    if mfa_required(user) and getattr(frappe.flags, 'dd_verified_mfa_user', None) != user:
        frappe.throw('Complete verification in Ground Scouts before signing in.', frappe.AuthenticationError)


def session_created(login_manager):
    user = login_manager.user
    if not is_scout(user):
        return
    payload = frappe.local.session_obj.data.data
    payload['dd_scout_started_at'] = now_datetime().isoformat()
    payload['dd_scout_mfa_verified'] = getattr(frappe.flags, 'dd_verified_mfa_user', None) == user
    frappe.local.session_obj.update(force=True)


def _public_recovery_request():
    request = getattr(frappe.local, 'request', None)
    path = getattr(request, 'path', '')
    method = getattr(request, 'method', '')
    if path == '/update-password' and method == 'GET':
        return True
    if method != 'POST':
        return False
    if path == '/api/method/frappe.core.doctype.user.user.reset_password':
        return True
    # The framework still validates the one-use reset key and password policy.
    return path == '/api/method/frappe.core.doctype.user.user.update_password' and bool(frappe.form_dict.get('key'))


def validate_session(user):
    if not is_scout(user):
        return
    if _public_recovery_request():
        return
    session = getattr(frappe.local, 'session_obj', None)
    data = getattr(session, 'data', None)
    payload = data.get('data') if isinstance(data, dict) else None
    # API tokens cannot bypass the expiry or second-factor requirement.
    if not isinstance(payload, dict) or not data.get('sid') or data.get('sid') == 'Guest':
        frappe.throw('Sign in to Ground Scouts again.', frappe.AuthenticationError)
    created = payload.get('dd_scout_started_at') or payload.get('creation')
    try:
        age = (now_datetime() - get_datetime(created)).total_seconds() if created else None
    except (TypeError, ValueError, OverflowError):
        age = None
    if age is None or age < -300 or age >= ABSOLUTE_SESSION_SECONDS:
        frappe.throw('Your sign-in has expired. Sign in again; saved work is retained.', frappe.AuthenticationError)
    if mfa_required(user) and payload.get('dd_scout_mfa_verified') is not True:
        frappe.throw('Complete verification in Ground Scouts before uploading.', frappe.AuthenticationError)


def configure_security(enable_scout_two_factor=False):
    """Explicit post-deployment configuration; never invoked by migration/handover."""
    frappe.only_for('System Manager')
    settings = frappe.get_single('System Settings')
    settings.allow_consecutive_login_attempts = 5
    settings.allow_login_after_fail = 300
    settings.logout_on_password_reset = 1
    if enable_scout_two_factor:
        if not frappe.db.exists('Role', 'Field Agent'):
            frappe.throw('Field Agent role is missing.')
        if settings.enable_two_factor_auth and settings.two_factor_method != 'Email':
            frappe.throw('Review the existing two-factor method before changing it.')
        settings.enable_two_factor_auth = 1
        settings.two_factor_method = 'Email'
        role = frappe.get_doc('Role', 'Field Agent')
        role.two_factor_auth = 1
        role.save(ignore_permissions=True)
    settings.save(ignore_permissions=True)
    frappe.clear_cache()
    return {'absolute_scout_session_seconds': ABSOLUTE_SESSION_SECONDS,
            'login_attempts': 5, 'retry_after_seconds': 300,
            'scout_two_factor_enabled': bool(enable_scout_two_factor)}
