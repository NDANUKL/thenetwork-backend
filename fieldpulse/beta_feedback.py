"""One immutable beta response per verified customer, via the website bridge."""
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import frappe
from fieldpulse.beta_access import require_access

CHOICES = {
    "legitimacy": ("Legit", "Not sure", "Sketchy"),
    "confusing": ("No", "Yes"),
    "deposit": ("Fine", "Unsure", "No way"),
    "pricing_clear": ("Yes", "No"),
    "would_use": ("Yes", "Maybe", "No"),
    "currency": ("KES", "USD", "GBP", "Other"),
}
TEXT_FIELDS = ("understanding", "trust_more", "nearly_stopped", "confusing_details", "use_case", "other_currency")


def validate_answers(raw):
    if isinstance(raw, str):
        if len(raw) > 65536:
            raise ValueError("Response too long")
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("Invalid response")
    result = {}
    for key, options in CHOICES.items():
        if raw.get(key) not in options:
            raise ValueError("Invalid choice")
        result[key] = raw[key]
    for key, low, high in (("proof_trust", 1, 5), ("scout_comfort", 1, 5), ("recommend", 0, 10)):
        value = raw.get(key)
        if isinstance(value, bool) or str(value) not in [str(i) for i in range(low, high + 1)]:
            raise ValueError("Invalid rating")
        result[key] = int(value)
    for key in TEXT_FIELDS:
        value = raw.get(key, "")
        if not isinstance(value, str) or len(value) > (40 if key == "other_currency" else 2000):
            raise ValueError("Invalid text")
        result[key] = value.strip()
    required = ["understanding", "trust_more", "nearly_stopped"]
    if result["confusing"] == "Yes":
        required.append("confusing_details")
    else:
        result["confusing_details"] = ""
    if result["would_use"] != "No":
        required.append("use_case")
    if result["currency"] == "Other":
        required.append("other_currency")
    else:
        result["other_currency"] = ""
    if any(not result[key] for key in required):
        raise ValueError("Missing answer")
    price = raw.get("fair_price")
    if isinstance(price, bool) or not isinstance(price, (str, int, float)) or len(str(price)) > 32:
        raise ValueError("Invalid price")
    try:
        amount = Decimal(str(price))
        if not amount.is_finite() or not 0 <= amount <= 1000000000 or amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Invalid price")
    except InvalidOperation as error:
        raise ValueError("Invalid price") from error
    result["fair_price"] = str(amount)
    return result


def bridge_account(email):
    # Match the existing server-only customer request bridge. A customer cannot
    # supply another identity directly through a Frappe website session.
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Not permitted", frappe.PermissionError)
    email = email.strip().lower() if isinstance(email, str) else ""
    account = frappe.db.exists("DD Customer Account", {"user": email, "email_verified": 1})
    user = frappe.get_doc("User", email) if account else None
    roles = [row.role for row in user.roles] if user else []
    if (not account or not user.enabled or user.user_type != "Website User" or "DD Customer" not in roles
            or any(frappe.db.get_value("Role", role, "desk_access") for role in roles)):
        frappe.throw("Not permitted", frappe.PermissionError)
    require_access(account)
    return account, user


@frappe.whitelist(methods=["POST"])
def dispatch(**kwargs):
    account, user = bridge_account(frappe.form_dict.get("email"))
    action = frappe.form_dict.get("action")
    if action not in ("status", "submit"):
        frappe.throw("Invalid action")
    if action == "submit":
        # Serialize submissions for this account. The unique database field is
        # a second guard; no explicit commit means ordinary request rollback applies.
        frappe.db.sql("SELECT name FROM `tabDD Customer Account` WHERE name=%s FOR UPDATE", (account,))
    # A normal SELECT can retain the snapshot taken by bridge_account before
    # waiting for the account lock. Use a current locking read for retries.
    submitted = bool(frappe.db.sql(
        "SELECT name FROM `tabDD Beta Feedback` WHERE customer_account=%s FOR UPDATE", (account,)
    )) if action == "submit" else bool(frappe.db.exists("DD Beta Feedback", {"customer_account": account}))
    eligible = bool(frappe.db.exists("Diaspora Request", {"dd_customer_account": account}))
    if action == "status" or submitted:
        return {"eligible": eligible, "submitted": submitted}
    if not eligible:
        return {"not_eligible": True}
    try:
        answers = validate_answers(frappe.form_dict.get("answers"))
    except (ValueError, TypeError):
        return {"invalid": True}
    # An ISO UTC Data field avoids Desk converting a UTC value as site-local time.
    doc = frappe.get_doc({"doctype": "DD Beta Feedback", **answers,
        "customer_account": account, "customer_name": user.full_name, "customer_email": user.name,
        "submitted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "form_version": "1"})
    doc.flags.beta_feedback_submission = True
    doc.insert(ignore_permissions=True)
    return {"eligible": True, "submitted": True}
