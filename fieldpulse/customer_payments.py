"""Compatibility API for the website's existing dd_payments and Pesapal callback routes."""
from fieldpulse.native_ownership import owned_api
import frappe
from fieldpulse.payments import (roles, csrf, mutation_proof, billing, accept_quote, checkout,
    refresh, register_ipn, withdraw_quote, ipn)
from fieldpulse.commerce import (disputes, create_dispute, report, download_report,
    update_settings, deletion_request)

@frappe.whitelist()
@owned_api('DD Customer Commerce')
def dispatch(**kwargs):
    action = frappe.form_dict.get("action")
    if action == "csrf":
        result = csrf()
    elif action == "billing":
        result = billing(frappe.form_dict.get("reference"))
    elif action == "disputes":
        result = disputes(frappe.form_dict.get("reference"))
    elif action == "report":
        result = report(frappe.form_dict.get("reference"))
    elif action == "download_report":
        result = download_report(frappe.form_dict.get("reference"))
    elif action in ["accept_quote", "checkout", "refresh", "create_dispute", "update_settings", "deletion_request"]:
        mutation_proof()
        if action == "accept_quote":
            result = accept_quote(frappe.form_dict.get("reference"), frappe.form_dict.get("quote"), frappe.form_dict.get("version"), frappe.form_dict.get("submission_id"))
        elif action == "checkout":
            result = checkout(frappe.form_dict.get("reference"), frappe.form_dict.get("payment"), frappe.form_dict.get("submission_id"), frappe.form_dict.get("return_origin"))
        elif action == "refresh":
            result = refresh(frappe.form_dict.get("reference"))
        elif action == "create_dispute":
            result = create_dispute(frappe.form_dict.get("reference"), frappe.form_dict.get("subject"), frappe.form_dict.get("reason"), frappe.form_dict.get("submission_id"))
        elif action == "update_settings":
            notifications = frappe.form_dict.get("email_notifications")
            if isinstance(notifications, str):
                notifications = notifications == "true"
            result = update_settings(frappe.form_dict.get("full_name"), frappe.form_dict.get("phone") or "", frappe.form_dict.get("timezone"), notifications)
        elif action == "deletion_request":
            result = deletion_request(frappe.form_dict.get("reason") or "")
    elif action == "configure_ipn":
        mutation_proof()
        result = register_ipn()
    elif action == "withdraw_quote":
        mutation_proof()
        result = withdraw_quote(frappe.form_dict.get("quote"))
    elif action == "configuration_status":
        if "System Manager" not in roles():
            frappe.throw("Not permitted", frappe.PermissionError)
        settings = frappe.get_doc("DD Payment Settings")
        result = {"enabled": bool(settings.enabled), "environment": settings.environment, "customer_origin": settings.customer_origin,
            "sandbox_key": bool(settings.get_password("sandbox_consumer_key", raise_exception=False)),
            "sandbox_secret": bool(settings.get_password("sandbox_consumer_secret", raise_exception=False)), "sandbox_ipn": bool(settings.sandbox_ipn_id)}
    else:
        frappe.throw("Invalid account action")
    if result is not None:
        frappe.response["message"] = result
    return frappe.response.pop("message", None)

@frappe.whitelist(allow_guest=True)
@owned_api('DD Pesapal IPN')
def notification(OrderTrackingId=None, OrderMerchantReference=None, OrderNotificationType=None):
    return ipn(OrderTrackingId, OrderMerchantReference, OrderNotificationType)
