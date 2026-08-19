"""Mobile account endpoints for Diaspora Desk field agents."""

import frappe
from frappe.utils import get_url, validate_email_address


def _login(email, password):
    login_manager = frappe.auth.LoginManager()
    login_manager.authenticate(user=email, pwd=password)
    login_manager.post_login()
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
    if not frappe.db.exists("FP Agent", {"user": email, "status": "Active"}):
        frappe.throw("This account is not an active field agent.")
    return _login(email, password)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_field_agent(full_name, email, password, phone=None):
    """Create a least-privilege Field Agent account for the mobile app."""
    email = validate_email_address((email or "").strip().lower(), throw=True)
    full_name = (full_name or "").strip()
    if len(full_name) < 2:
        frappe.throw("Enter your full name.")
    if not password or len(password) < 8:
        frappe.throw("Use a password with at least 8 characters.")
    if frappe.db.exists("User", email):
        frappe.throw("An account with this email already exists. Sign in instead.")

    user = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": full_name,
        "send_welcome_email": 0,
        "new_password": password,
        "roles": [{"role": "Field Agent"}],
    })
    user.insert(ignore_permissions=True)
    agent = frappe.get_doc({
        "doctype": "FP Agent",
        "agent_code": f"AGT-{frappe.generate_hash(length=8).upper()}",
        "user": user.name,
        "full_name": full_name,
        "phone": phone,
        "status": "Active",
    })
    agent.insert(ignore_permissions=True)
    frappe.db.commit()
    return _login(email, password)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def request_password_reset(email):
    """Send a branded Ground Scouts password-reset email to active field agents."""
    email = validate_email_address((email or "").strip().lower(), throw=True)

    if not frappe.db.exists("User", email):
        return {"message": "If this email is registered, reset instructions will be sent."}

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
