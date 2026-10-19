"""Retryable approval delivery using the website's verified Resend sender."""
import json
from html import escape
from pathlib import Path
from urllib.parse import urlsplit
import requests
import frappe


def render_approval(origin):
    values = dict(origin=origin, title="Your early access is ready", eyebrow="WELCOME ABOARD",
        preheader="You're invited to start your journey with Diaspora Desk.",
        body="Good news, your Diaspora Desk account has been approved. Log in to start your first request and follow its progress from your desk.",
        link=origin + "/request", label="Log in to your desk",
        note="Use the email address and password you registered with.")
    shell = json.loads((Path(__file__).parent / "templates/emails/dd_shell.json").read_text(encoding="utf-8"))
    import re
    return re.sub(r"{{(\w+)}}", lambda match: escape(values[match[1]], quote=True), shell)


def send_approval(account_name):
    # Serialize delivery and approval/rejection updates on this account.
    frappe.db.sql("SELECT name FROM `tabDD Customer Account` WHERE name=%s FOR UPDATE", [account_name])
    account = frappe.get_doc("DD Customer Account", account_name)
    if account.get("beta_access") != "Approved" or not account.get("approval_email_id") or account.get("approval_email_sent_at") or not account.email_verified:
        return
    settings = frappe.get_doc("DD Access Settings")
    key = settings.get_password("resend_api_key", raise_exception=False)
    origin = (settings.customer_origin or "").rstrip("/")
    parsed = urlsplit(origin)
    if not key or not settings.resend_from_email or parsed.scheme != "https" or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
        frappe.throw("Configure the website origin and email delivery in DD Access Settings")
    response = requests.post("https://api.resend.com/emails", timeout=20,
        headers={"Authorization": "Bearer " + key, "Idempotency-Key": "dd-access-" + account.approval_email_id},
        json={"from": settings.resend_from_email, "to": [account.user], "subject": "Your Diaspora Desk early access is ready",
              "html": render_approval(origin), "text": "Good news, your account is approved. Log in to start your journey: " + origin + "/request"})
    if not response.ok:
        # Do not put provider response bodies, recipient addresses or credentials in logs.
        frappe.throw("Approval email delivery failed; it will be retried")
    account.db_set("approval_email_sent_at", frappe.utils.now_datetime(), update_modified=False)


def retry_approvals():
    for row in frappe.get_all("DD Customer Account", filters={"beta_access": "Approved", "email_verified": 1,
            "approval_email_sent_at": ["is", "not set"], "approval_email_id": ["is", "set"]}, pluck="name", limit_page_length=100):
        frappe.enqueue("fieldpulse.access_notifications.send_approval", account_name=row)
