"""Durable, preference-aware customer milestone emails via the shared Resend sender."""
import hashlib
import json
import re
from datetime import timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote, urlsplit
import requests
import frappe
from fieldpulse.beta_access import access_status

DOCTYPE = "DD Customer Notification"
SOURCE_TYPES = {"details": "DD Request Details", "quotation": "DD Quotation", "payment": "DD Payment", "report": "DD Service Report", "dispute": "DD Dispute", "recurring": "DD Recurring Occurrence"}


def digest(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def request_reference(doc):
    return doc.get('source_request') if doc.get('doctype') == 'DD Recurring Occurrence' else doc.request


def current_event(kind, doc):
    if kind == "recurring":
        return doc.status == 'Awaiting access' and frappe.db.get_value('DD Recurring Plan',doc.plan,'status') == 'Active' and str(doc.window_end) >= str(frappe.utils.today())
    if kind == "details": return doc.status == "Details needed" and not doc.get("email_sent_at")
    if kind == "quotation": return doc.status == "Issued"
    if kind == "report": return doc.status == "Approved" and bool(doc.get("report_file"))
    if kind == "dispute": return bool((doc.get("response") or "").strip())
    if kind == "payment":
        from fieldpulse.payment_receipts import verified_attempt
        return bool(verified_attempt(doc))
    return False


def revision(kind, doc):
    if kind == "recurring": return str(frappe.db.get_value("DD Recurring Plan",doc.plan,"modified"))
    if kind == "dispute": return digest((doc.response or "").strip())
    if kind == "payment": return doc.get("paid_attempt") or ""
    return str(doc.get("version") or doc.get("report_version") or 1)


def eligible(account):
    return bool(account.email_verified and account.email_notifications
        and access_status(account) == "Approved"
        and frappe.db.get_value("User", account.user, "enabled"))


def queue_event(kind, doc):
    if not frappe.conf.get("dd_native_handover_approved") or not current_event(kind, doc): return None
    request = frappe.get_doc("Diaspora Request", request_reference(doc))
    if not request.get("dd_customer_account"): return None
    account = frappe.get_doc("DD Customer Account", request.dd_customer_account)
    if not eligible(account): return None
    key = digest(":".join([kind, doc.name, revision(kind, doc)]))
    # Serialize milestone capture for this request, including concurrent callbacks.
    frappe.db.sql("SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE", [request.name])
    if frappe.db.exists(DOCTYPE, key): return key
    frappe.get_doc({"doctype": DOCTYPE, "event_key": key, "kind": kind,
        "request": request.name, "customer_account": account.name,
        "source_type": SOURCE_TYPES[kind], "source_name": doc.name,
        "source_revision": revision(kind, doc), "status": "Pending", "attempts": 0,
        "next_attempt_at": frappe.utils.now_datetime()}).insert(ignore_permissions=True)
    enqueue(key)
    return key


def capture(doc, method=None):
    if frappe.flags.in_migrate or frappe.flags.in_install: return
    kind = next((kind for kind, dt in SOURCE_TYPES.items() if dt == doc.doctype), None)
    if not kind: return
    old = doc.get_doc_before_save()
    if kind in ("details", "quotation", "report") and old and old.status == doc.status: return
    if kind == "dispute" and old and (old.response or "").strip() == (doc.response or "").strip(): return
    return queue_event(kind, doc)


def enqueue(name):
    try:
        frappe.enqueue("fieldpulse.customer_notifications.send", notification=name, enqueue_after_commit=True)
    except Exception:
        # The durable Pending row survives an unavailable Redis queue; cron retries it.
        pass


def event_message(kind, doc, reference, origin):
    reference_path = quote(reference, safe="")
    messages = {
        "details": ("More details needed", "Your coordinator needs a few more details to move your request forward.", f"/dashboard/requests/{reference_path}#details-needed", "Answer the questions"),
        "quotation": ("Your quotation is ready", "Your quotation is ready. Review its scope and price, download it, and accept it when you are ready to proceed.", f"/dashboard/billing/{reference_path}", "Review quotation"),
        "report": ("Your verification report is ready", "Your approved report is ready to download. Review it before paying the remaining balance. If anything needs attention, you can raise a dispute from your request.", f"/dashboard/requests/{reference_path}#report", "Review your report"),
        "dispute": ("A response to your dispute", "Our team has responded to your dispute. Open it to read the reply and any next steps.", f"/dashboard/disputes/{quote(doc.name, safe='')}", "Read the response"),
    }
    if kind == "recurring":
        title, body, path, label = ("Confirm access for your upcoming check",
            f"Your recurring visit is scheduled for {doc.due_date} to {doc.window_end}. Confirm access and review the arrangements. Each visit needs its own accepted quotation and verified deposit before dispatch.",
            f"/dashboard/recurring/{quote(doc.plan,safe='')}", "Review upcoming check")
        values = dict(origin=origin, title=title, eyebrow="RECURRING CHECK", preheader=title,
            body=body,link=origin+path,label=label,note="Manage your recurring plan and email preferences from your dashboard.")
        shell=json.loads((Path(__file__).parent / "templates/emails/dd_shell.json").read_text(encoding="utf-8"))
        return {"subject":title,"html":re.sub(r"{{(\w+)}}",lambda m:escape(values[m[1]],quote=True),shell),"text":body+"\n\n"+values['link']}
    if kind == "payment":
        from fieldpulse.payment_receipts import verified_attempt
        attempt = verified_attempt(doc)
        test = attempt.environment != "live"
        label = "deposit" if doc.kind == "deposit" else "balance"
        title = "Test payment confirmed" if test else "Payment confirmed"
        body = f"Your {label} payment of {doc.currency} {float(doc.amount):,.2f} has been verified. Your receipt is available in Billing."
        if test: body = "This was a sandbox test; no live payment was received. " + body
        title, body, path, label = title, body, f"/dashboard/billing/{reference_path}#receipts", "View receipt"
    else:
        title, body, path, label = messages[kind]
    values = dict(origin=origin, title=title, eyebrow="REQUEST UPDATE", preheader=title + " - " + reference,
        body=body + " Request: " + reference + ".", link=origin + path, label=label,
        note="Manage important request email preferences from Account in your dashboard.")
    shell = json.loads((Path(__file__).parent / "templates/emails/dd_shell.json").read_text(encoding="utf-8"))
    html = re.sub(r"{{(\w+)}}", lambda match: escape(values[match[1]], quote=True), shell)
    return {"subject": title + " - " + reference, "html": html, "text": values["body"] + "\n\n" + values["link"]}


def delivery_config():
    settings = frappe.get_doc("DD Access Settings")
    origin = (settings.customer_origin or "").rstrip("/")
    parsed = urlsplit(origin)
    key = settings.get_password("resend_api_key", raise_exception=False)
    if (not key or not settings.resend_from_email or parsed.scheme != "https" or not parsed.hostname
            or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("Configure email sender, Resend key and HTTPS website origin in DD Access Settings")
    return key, settings.resend_from_email, origin


def send(notification):
    if not frappe.conf.get("dd_native_handover_approved"): return
    frappe.db.sql("SELECT name FROM `tabDD Customer Notification` WHERE name=%s FOR UPDATE", [notification])
    record = frappe.get_doc(DOCTYPE, notification)
    now = frappe.utils.now_datetime()
    if record.status != "Pending" or (record.next_attempt_at and frappe.utils.get_datetime(record.next_attempt_at) > now): return
    doc = frappe.get_doc(record.source_type, record.source_name)
    request = frappe.get_doc("Diaspora Request", record.request)
    account = frappe.get_doc("DD Customer Account", record.customer_account)
    if (request_reference(doc) != record.request or request.dd_customer_account != account.name or not eligible(account)
            or not current_event(record.kind, doc) or revision(record.kind, doc) != record.source_revision):
        frappe.db.set_value(DOCTYPE, record.name, "status", "Skipped")
        return
    # Resend retains idempotency keys for 24h. Do not automatically resend an
    # uncertain delivery after that window; leave it for operator review instead.
    if record.first_attempt_at and now - frappe.utils.get_datetime(record.first_attempt_at) >= timedelta(hours=23):
        frappe.db.set_value(DOCTYPE, record.name, {"status": "Needs review", "last_error": "Delivery outcome needs review; retry window expired."})
        return
    attempts = int(record.attempts or 0) + 1
    try:
        key, sender, origin = delivery_config()
        payload = json.loads(record.payload) if record.get("payload") else {
            "from": sender, "to": [account.user], **event_message(record.kind, doc, record.request, origin)}
        # Freeze the exact provider payload before sending; all retries use it.
        frappe.db.set_value(DOCTYPE, record.name, {"payload": json.dumps(payload), "first_attempt_at": record.first_attempt_at or now, "attempts": attempts})
        frappe.db.commit()
        # Keep the record locked across provider delivery so duplicate workers wait.
        frappe.db.sql("SELECT name FROM `tabDD Customer Notification` WHERE name=%s FOR UPDATE", [notification])
        record.reload()
        if record.status != "Pending": return
        account.reload()
        doc.reload()
        if (not eligible(account) or payload["to"] != [account.user]
                or not current_event(record.kind, doc) or revision(record.kind, doc) != record.source_revision):
            frappe.db.set_value(DOCTYPE, record.name, "status", "Skipped")
            return
        response = requests.post("https://api.resend.com/emails", timeout=20,
            headers={"Authorization": "Bearer " + key, "Idempotency-Key": "dd-update-" + record.name}, json=payload)
        if not response.ok or not response.json().get("id"): raise ValueError("Email provider did not accept the message")
        frappe.db.set_value(DOCTYPE, record.name, {"status": "Sent", "sent_at": frappe.utils.now_datetime(),
            "provider_id": response.json()["id"], "last_error": ""})
        if record.kind == "details":
            frappe.db.set_value("DD Request Details", doc.name, "email_sent_at", frappe.utils.now_datetime(), update_modified=False)
    except Exception:
        frappe.db.set_value(DOCTYPE, record.name, {"attempts": attempts,
            "status": "Needs review" if attempts >= 8 else "Pending",
            "next_attempt_at": now + timedelta(minutes=min(60, 5 * 2 ** (attempts - 1))),
            "last_error": "Email not confirmed. Check DD Access Settings, Resend and worker availability."})


def retry_pending():
    if not frappe.conf.get("dd_native_handover_approved"): return
    # Repair the old webhook-only details flow, including currently unanswered rounds.
    rows = frappe.db.sql("""SELECT d.name FROM `tabDD Request Details` d
        JOIN `tabDiaspora Request` r ON r.name=d.request
        JOIN `tabDD Customer Account` a ON a.name=r.dd_customer_account
        WHERE d.status='Details needed' AND d.email_sent_at IS NULL
        AND a.email_verified=1 AND a.email_notifications=1
        ORDER BY d.published_at DESC LIMIT 100""", as_dict=True)
    for row in rows:
        queue_event("details", frappe.get_doc("DD Request Details", row.name))
    for name in frappe.get_all(DOCTYPE, filters={"status": "Pending", "next_attempt_at": ["<=", frappe.utils.now_datetime()]},
            pluck="name", order_by="next_attempt_at asc", limit_page_length=100):
        enqueue(name)


@frappe.whitelist()
def delivery_status():
    """Admin diagnostics expose presence and counts, never credentials or recipients."""
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted", frappe.PermissionError)
    settings = frappe.get_doc("DD Access Settings")
    configured = True
    try:
        delivery_config()
    except ValueError:
        configured = False
    return {"configured": configured,
        "sender_configured": bool(settings.resend_from_email),
        "key_configured": bool(settings.get_password("resend_api_key", raise_exception=False)),
        "pending": frappe.db.count(DOCTYPE, {"status": "Pending"}),
        "needs_review": frappe.db.count(DOCTYPE, {"status": "Needs review"})}


@frappe.whitelist(methods=["POST"])
def retry_notification(notification):
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Not permitted", frappe.PermissionError)
    frappe.db.sql("SELECT name FROM `tabDD Customer Notification` WHERE name=%s FOR UPDATE", [notification])
    record = frappe.get_doc(DOCTYPE, notification)
    if record.status == "Sent": return {"success": True, "status": "Sent"}
    if record.first_attempt_at and frappe.utils.now_datetime() - frappe.utils.get_datetime(record.first_attempt_at) >= timedelta(hours=23):
        frappe.throw("Check this message in Resend before taking further action; its safe retry window has expired.")
    frappe.db.set_value(DOCTYPE, record.name, {"status": "Pending", "attempts": 0,
        "next_attempt_at": frappe.utils.now_datetime(), "last_error": ""})
    enqueue(record.name)
    return {"success": True, "status": "Pending"}
