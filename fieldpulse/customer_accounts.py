"""Native customer accounts behavior, ported from the audited production definitions."""
import json
import frappe
from fieldpulse.native_ownership import owned_event, owned_api
from fieldpulse.beta_access import registration_access, access_status

@frappe.whitelist()
@owned_api('DD Customer Registration Bridge')
def registration(**kwargs):
    # Called only by the authenticated DD server. Never enable guest access.
    if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "parenttype": "User", "role": "System Manager"}):
        frappe.throw("Not permitted", frappe.PermissionError)
    
    action = frappe.form_dict.get("action")
    email = (frappe.form_dict.get("email") or "").strip().lower()
    if not email or len(email) > 254 or "@" not in email:
        frappe.throw("Invalid account")
    
    profile_name = frappe.db.exists("DD Customer Account", {"user": email})
    profile = frappe.get_doc("DD Customer Account", profile_name) if profile_name else None
    user = frappe.get_doc("User", email) if frappe.db.exists("User", email) else None
    eligible = bool(profile and user and user.user_type == "Website User" and "DD Customer" in [row.role for row in user.roles])
    # Even if someone later grants a desk role, this bridge must fail closed.
    if eligible:
        for row in user.roles:
            if frappe.db.get_value("Role", row.role, "desk_access"):
                eligible = False

    # A retained deactivated identity cannot be re-enabled by repeat signup,
    # an old verification link, recovery, or the server-side profile bridge.
    if profile and profile.get("account_access") == "Deactivated":
        if action in ("register", "recover"):
            return {"eligible": False}
        frappe.throw("This account has been deactivated. Contact Diaspora Desk.", frappe.PermissionError)
    
    if action == "register":
        if user:
            frappe.response["message"] = {"eligible": bool(eligible and not profile.email_verified and not user.enabled)}
        else:
            full_name = (frappe.form_dict.get("full_name") or "").strip()
            if not full_name or len(full_name) > 140:
                frappe.throw("Invalid account")
            user = frappe.get_doc({"doctype": "User", "email": email, "first_name": full_name,
                "enabled": 0, "send_welcome_email": 0, "roles": [{"role": "DD Customer"}]})
            user.insert()
            profile = frappe.get_doc({"doctype": "DD Customer Account", "user": email,
                "beta_access": "Pending" if registration_access() == "Invite only" else "Approved",
                "email_verified": 0, "accepted_terms_at": frappe.utils.now_datetime(), "email_notifications": 1})
            profile.insert()
            frappe.response["message"] = {"eligible": True}
    elif action == "verify":
        if not eligible:
            frappe.throw("Invalid account", frappe.PermissionError)
        if not profile.email_verified and not user.enabled:
            password = frappe.form_dict.get("password") or ""
            if len(password) < 8 or len(password) > 128 or not any("a" <= char <= "z" for char in password) or not any("A" <= char <= "Z" for char in password) or not any("0" <= char <= "9" for char in password):
                frappe.throw("Invalid password")
            user.new_password = password
            user.enabled = 1
            user.send_welcome_email = 0
            user.save()
            profile.email_verified = 1
            profile.verified_at = frappe.utils.now_datetime()
            profile.save()
        if not profile.email_verified or not user.enabled:
            frappe.throw("Invalid account", frappe.PermissionError)
        frappe.response["message"] = {"verified": True, "access_status": access_status(profile)}
    elif action == "profile":
        if not eligible or not profile.email_verified or not user.enabled:
            frappe.throw("Invalid account", frappe.PermissionError)
        frappe.response["message"] = {"customer": {"id": profile.name, "email": email,
            "full_name": user.full_name, "email_verified": True, "access_status": access_status(profile), "phone": user.mobile_no,
            "timezone": user.time_zone, "email_notifications": bool(profile.email_notifications)}}
    elif action == "recover":
        if eligible and profile.email_verified and user.enabled:
            digest = frappe.form_dict.get("digest") or ""
            if len(digest) != 64:
                frappe.throw("Invalid reset token")
            user.db_set("reset_password_key", digest)
            user.db_set("last_reset_password_key_generated_on", frappe.utils.now_datetime())
            frappe.response["message"] = {"eligible": True}
        else:
            frappe.response["message"] = {"eligible": False}
    else:
        frappe.throw("Invalid action")
    return frappe.response.pop("message", None)
