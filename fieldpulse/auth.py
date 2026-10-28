"""Mobile account endpoints for Diaspora Desk field agents."""

import hashlib
import hmac
from contextlib import nullcontext

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url, validate_email_address


def _login(email, password=None, otp=None, tmp_id=None):
    try:
        return _perform_login(email, password, otp, tmp_id)
    finally:
        for field in ('pwd', 'password', 'otp', 'tmp_id'):
            frappe.form_dict.pop(field, None)


def _perform_login(email, password=None, otp=None, tmp_id=None):
    from frappe.twofactor import get_cached_user_pass, should_run_2fa

    class MobileLoginManager(frappe.auth.LoginManager):
        def post_login(self, *args, **kwargs):
            # login() calls this only after the framework verifies the second factor.
            verified = self.user if otp and tmp_id and should_run_2fa(self.user) else None
            old = getattr(frappe.flags, 'dd_verified_mfa_user', None)
            frappe.flags.dd_verified_mfa_user = verified
            try:
                return super().post_login(*args, **kwargs)
            finally:
                frappe.flags.dd_verified_mfa_user = old

    if tmp_id or otp:
        if (not isinstance(tmp_id, str) or not 8 <= len(tmp_id) <= 128
                or not isinstance(otp, str) or len(otp) != 6 or not otp.isascii() or not otp.isdigit()):
            frappe.throw('Invalid or expired verification. Sign in again.', frappe.AuthenticationError)
        lock_key = 'dd-mobile-otp:' + hashlib.sha256(tmp_id.encode()).hexdigest()
        guard = frappe.cache().lock(lock_key, timeout=20, blocking_timeout=5)
    else:
        if not isinstance(password, str) or not password or len(password) > 512:
            frappe.throw('Email and password are required.', frappe.AuthenticationError)
        guard = nullcontext()

    with guard:
        if tmp_id:
            frappe.form_dict['tmp_id'] = tmp_id
            frappe.form_dict['otp'] = otp
            cached_user, cached_password = get_cached_user_pass()
            if (not isinstance(cached_user, str) or not cached_password
                    or not hmac.compare_digest(cached_user.strip().lower(), email)):
                frappe.throw('Invalid or expired verification. Sign in again.', frappe.AuthenticationError)
            # Never accept fresh credentials as a substitute for the pinned challenge.
            frappe.form_dict.pop('usr', None)
            frappe.form_dict.pop('pwd', None)
        else:
            frappe.form_dict.pop('tmp_id', None)
            frappe.form_dict.pop('otp', None)
            frappe.form_dict['usr'] = email
            frappe.form_dict['pwd'] = password
        manager = MobileLoginManager()
        frappe.local.login_manager = manager
        try:
            completed = manager.login()
        finally:
            frappe.form_dict.pop('pwd', None)
            frappe.form_dict.pop('password', None)
        if completed is False:
            verification = frappe.local.response.get('verification')
            challenge = frappe.local.response.get('tmp_id')
            if not isinstance(verification, dict) or not challenge:
                frappe.throw('Reset your password before signing in.', frappe.AuthenticationError)
            method = verification.get('method')
            if verification.get('token_delivery') is False or method not in ('Email', 'SMS', 'OTP App'):
                frappe.throw('Verification is unavailable. Contact your coordinator.', frappe.AuthenticationError)
            return {'two_factor_required': True, 'tmp_id': challenge, 'method': method,
                    'expires_in': 180 if method == 'OTP App' else 300}
        if manager.user.strip().lower() != email or frappe.session.user == 'Guest':
            frappe.throw('Sign-in was not confirmed.', frappe.AuthenticationError)
        if tmp_id:
            for suffix in ('_usr', '_pwd', '_token', '_otp_secret'):
                frappe.cache().delete_value(tmp_id + suffix)
    profile = frappe.db.exists('Scout Profile', {'user': email})
    if profile:
        from frappe.utils import now_datetime
        frappe.db.set_value('Scout Profile', profile, {
            'last_app_activity': now_datetime(), 'activity_status': 'Active',
        }, update_modified=False)
    return {'sid': frappe.session.sid,
            'full_name': frappe.db.get_value('User', email, 'full_name') or email}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def mobile_login(email, password=None, otp=None, tmp_id=None):
    """Return a Frappe session ID for a verified Field Agent."""
    email = (email or "").strip().lower()
    if not email or not (password or (otp and tmp_id)):
        frappe.throw("Email and password are required.")
    from fieldpulse.scout_access import check_access
    check_access(email)
    if not frappe.db.exists("Scout Profile", {"user": email}):
        frappe.throw("Your scout application must be approved before signing in.")
    if not frappe.db.exists("FP Agent", {"user": email, "status": "Active"}):
        frappe.throw("This account is not an active field agent.")
    return _login(email, password, otp, tmp_id)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_field_agent(full_name, email, password, phone=None, county=None):
    """Submit an application; no scout role, profile or session until staff approval."""
    email = validate_email_address((email or "").strip().lower(), throw=True)
    full_name = " ".join((full_name or "").split())
    county = " ".join((county or "").split())
    if (len(full_name.split()) < 2 or len(full_name) > 140
            or not all(any(char.isalpha() for char in part) for part in full_name.split())
            or any(char in full_name for char in "<>")):
        frappe.throw("Enter your full name (at least two names).")
    if not county or len(county) > 100 or any(char in county for char in "<>"):
        frappe.throw("Enter your county (up to 100 characters).")
    if not password or len(password) < 8:
        frappe.throw("Use a password with at least 8 characters.")
    phone = (phone or "").strip()
    if len(phone) > 40 or any(char not in "+0123456789 ()-" for char in phone):
        frappe.throw("Enter a valid phone number (up to 40 characters).")
    if frappe.db.exists("Scout Application", {"email": email}):
        frappe.throw("An application already exists for this email. Contact Diaspora Desk for its status.")
    if frappe.db.exists("User", email):
        frappe.throw("An account with this email already exists. Sign in or contact Diaspora Desk.")

    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": full_name,
        "send_welcome_email": 0,
        "new_password": password,
        "enabled": 0,
        "user_type": "Website User",
        "roles": [],
    })
    user.insert(ignore_permissions=True)
    from fieldpulse.scout_access import admission_write
    with admission_write():
        frappe.get_doc({
            "doctype": "Scout Application", "user": user.name, "email": email,
            "full_name": full_name, "phone": phone, "county": county, "status": "Pending",
        }).insert(ignore_permissions=True)
    return {"status": "Pending", "message": "Application submitted. You can sign in after Diaspora Desk approves your application."}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
@rate_limit(key='email', limit=3, seconds=3600)
def request_password_reset(email):
    """Send recovery instructions only for an email linked to a Scout Profile."""
    email = validate_email_address((email or "").strip().lower(), throw=True)

    # Profile membership is the sole account eligibility rule for recovery.
    # Recovery does not change account admission or sign-in permissions.
    if not frappe.db.exists("Scout Profile", {"user": email}):
        return {"message": "If this email is registered, reset instructions will be sent."}
    user = frappe.get_doc("User", email)

    reset_link = user._reset_password(send_email=False)
    full_name = user.full_name or email
    html = frappe.render_template(
        "fieldpulse/templates/emails/password_reset.html",
        {"full_name": full_name, "reset_link": reset_link, "site_url": get_url()},
    )

    frappe.sendmail(
        recipients=[email],
        subject="Reset your Ground Scouts password",
        message=html,
        delayed=False,
        retry=0,
    )
    frappe.db.commit()
    return {"message": "If this email is registered, reset instructions will be sent."}
