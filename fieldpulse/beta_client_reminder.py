"""Render the one-time client reminder without scheduling delivery."""

from html import escape
from pathlib import Path
from string import Template

from fieldpulse.email_branding import render_email

SUBJECT = "Thank you for testing Diaspora Desk"
TEMPLATE = Path(__file__).parent / "templates/emails/beta_client_reminder.html"


def render_reminder(*, first_name, origin):
    origin = (origin or "https://diaspora-desk.com").rstrip("/")
    name = escape((first_name or "").strip() or "there", quote=True)
    body = Template(TEMPLATE.read_text(encoding="utf-8")).substitute(first_name=name)
    return render_email(
        title=SUBJECT,
        body=body,
        body_is_html=True,
        origin=origin,
        link=f"{origin}/request",
        label="Log in",
        note="Thank you for helping shape Diaspora Desk.\nThe Diaspora Desk team",
    )


def queue_existing_clients(before, dry_run=True):
    """Preview or queue one reminder per eligible account created before a site-local cutoff."""
    import frappe

    from fieldpulse.customer_notifications import DOCTYPE, delivery_config, digest, eligible, enqueue

    if type(dry_run) is not bool:
        raise ValueError("dry_run must be a boolean")
    cutoff = frappe.utils.get_datetime(before) if before else None
    if not cutoff or cutoff > frappe.utils.now_datetime():
        raise ValueError("Supply an existing-client cutoff at or before the current time")
    if not dry_run:
        if not frappe.conf.get("dd_native_handover_approved"):
            raise ValueError("Native customer email delivery is not enabled")
        delivery_config()

    accounts = frappe.get_all(
        "DD Customer Account",
        filters={"creation": ["<", cutoff], "email_verified": 1, "email_notifications": 1},
        pluck="name",
        order_by="name asc",
    )
    counts = {"ready": 0, "already_queued": 0, "skipped": 0}
    for name in accounts:
        if not dry_run:
            frappe.db.sql("SELECT name FROM `tabDD Customer Account` WHERE name=%s FOR UPDATE", [name])
        account = frappe.get_doc("DD Customer Account", name)
        key = digest(f"beta_reminder:1:{name}")
        if frappe.db.exists(DOCTYPE, key):
            counts["already_queued"] += 1
        elif not eligible(account):
            counts["skipped"] += 1
        else:
            if not dry_run:
                # The outbox event key remains unique across reruns and worker retries.
                frappe.get_doc({
                    "doctype": DOCTYPE, "event_key": key, "kind": "beta_reminder",
                    "customer_account": name, "source_type": "DD Customer Account",
                    "source_name": name, "source_revision": "1", "status": "Pending",
                    "attempts": 0, "next_attempt_at": frappe.utils.now_datetime(),
                }).insert(ignore_permissions=True)
                enqueue(key)
            counts["ready"] += 1
    return {"dry_run": dry_run, **counts}
