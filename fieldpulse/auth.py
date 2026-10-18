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
    if not frappe.db.exists("FP Agent", {"user": email, "status": "Active"}):
        frappe.throw("This account is not an active field agent.")
    return _login(email, password)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_field_agent(full_name, email, password, phone=None, county=None):
    """Create a least-privilege Field Agent account for the mobile app."""
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
    # User/agent hooks may already have created this profile. Complete it in
    # the same transaction so registration never loses the scout's county.
    profile_name = frappe.db.exists("Scout Profile", {"user": user.name})
    profile = frappe.get_doc("Scout Profile", profile_name) if profile_name else frappe.get_doc({
        "doctype": "Scout Profile", "user": user.name, "availability_status": "Available",
    })
    profile.scout_name = full_name
    profile.base_county = county
    profile.phone_number = phone or ""
    profile.legacy_fp_agent = agent.name
    profile.save(ignore_permissions=True)
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
