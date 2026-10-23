"""Owned payment receipts backed by a verified Pesapal payment attempt."""
from pathlib import Path
from urllib.parse import quote as urlquote
import frappe
from fieldpulse.payment_rules import money


def verified_attempt(payment):
    if payment.status != "Paid" or not payment.get("paid_attempt") or not payment.get("paid_at"):
        return None
    attempt = frappe.get_doc("DD Payment Attempt", payment.paid_attempt)
    if (attempt.payment != payment.name or attempt.status != "Paid"
            or not attempt.get("verified_at") or not attempt.get("confirmation_code")
            or attempt.currency != payment.currency or money(attempt.amount) != money(payment.amount)):
        return None
    return attempt


def receipt_document(payment, reference):
    if payment.request != reference or not verified_attempt(payment):
        return None
    label = "Deposit receipt" if payment.kind == "deposit" else "Balance receipt"
    return {"name": "RCP-" + payment.name, "title": label, "kind": "receipt",
        "download_url": "/api/customer/requests/" + urlquote(reference, safe="") + "/receipts/" + urlquote(payment.name, safe="")}


def receipt_context(payment, quote, attempt):
    return {"receipt_number": "RCP-" + payment.name, "reference": payment.request,
        "quotation": payment.quotation, "customer_name": quote.customer_name,
        "customer_email": quote.customer_email, "paid_at": payment.paid_at,
        "currency": payment.currency, "amount": float(money(payment.amount)),
        "payment_label": "50% deposit" if payment.kind == "deposit" else "50% balance",
        "confirmation": attempt.confirmation_code, "test_payment": attempt.environment != "live",
        "projects": [item.project_title for item in (quote.get("items") or [])]}


@frappe.whitelist()
def download_receipt(reference, payment):
    from fieldpulse.payments import _owned
    from fieldpulse.quotation_pdf import quotation_assets, render_quotation_pdf
    request = _owned(reference)
    name = frappe.db.exists("DD Payment", {"name": payment, "request": request.name})
    if not name:
        frappe.throw("Receipt is not available", frappe.DoesNotExistError)
    obligation = frappe.get_doc("DD Payment", name)
    attempt = verified_attempt(obligation)
    quote = frappe.get_doc("DD Quotation", obligation.quotation)
    if not attempt or quote.request != request.name:
        frappe.throw("Receipt is not available", frappe.DoesNotExistError)
    template = (Path(__file__).parent / "templates/payment_receipt.html").read_text(encoding="utf-8")
    html = frappe.render_template(template, {"receipt": receipt_context(obligation, quote, attempt),
        "quotation_assets": quotation_assets()})
    content = render_quotation_pdf('<html><head><meta charset="utf-8"></head><body><div class="print-format">' + html + '</div></body></html>')
    frappe.response.update(type="download", filename="RCP-" + obligation.name + ".pdf",
        filecontent=content, display_content_as="attachment")
