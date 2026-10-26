"""Mobile account endpoints for Diaspora Desk field agents."""

import frappe
from frappe.utils import get_url, validate_email_address


def _login(email, password):
    login_manager = frappe.auth.LoginManager()
    login_manager.authenticate(user=email, pwd=password)
    login_manager.post_login()
    profile = frappe.db.exists("Scout Profile", {"user": email})
    if profile:
        from frappe.utils import now_datetime
        frappe.db.set_value("Scout Profile", profile, {
            "last_app_activity": now_datetime(), "activity_status": "Active",
        }, update_modified=False)
    return {
        "sid": frappe.session.sid,
        "full_name": frappe.db.get_value("User", email, "full_name") or email,
    }


@frappe.whitelist(allow_guest=True, methods=["POST"])
def mobile_login(email, password):
    """Return a Frappe session ID for a verified Field Agent."""
    email = (email or "").strip().lower()
    if not email or not password:
        frappe.throw("Email and password are required.")
    from fieldpulse.scout_access import check_access
    check_access(email)
    if not frappe.db.exists("Scout Profile", {"user": email}):
        frappe.throw("Your scout application must be approved before signing in.")
    if not frappe.db.exists("FP Agent", {"user": email, "status": "Active"}):
        frappe.throw("This account is not an active field agent.")
    return _login(email, password)


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
def request_password_reset(email):
    """Send a branded Ground Scouts password-reset email to active field agents."""
    email = validate_email_address((email or "").strip().lower(), throw=True)

    if not frappe.db.exists("User", email):
        return {"message": "If this email is registered, reset instructions will be sent."}

    from fieldpulse.scout_access import check_access
    check_access(email)

    if not frappe.db.exists("FP Agent", {"user": email, "status": "Active"}):
        frappe.throw("This account is not an active field agent.")

    user = frappe.get_doc("User", email)
    if not user.enabled:
        frappe.throw("This account is disabled. Contact your supervisor.")

    reset_link = user._reset_password(send_email=False)
    full_name = user.full_name or email
    html = frappe.render_template(
        "emails/password_reset.html",
        {"full_name": full_name, "reset_link": reset_link, "site_url": get_url()},
    )

    frappe.sendmail(
        recipients=[email],
        subject="Reset your Ground Scouts passcode",
        message=html,
        delayed=False,
        retry=0,
    )
    frappe.db.commit()
    return {"message": "If this email is registered, reset instructions will be sent."}
