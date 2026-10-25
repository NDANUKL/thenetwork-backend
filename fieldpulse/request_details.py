"""Native request details behavior, ported from the audited production definitions."""
import json
import frappe
from fieldpulse.native_ownership import owned_event, owned_api

@frappe.whitelist()
@owned_api('DD Details Notifications')
def notifications(**kwargs):
    if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "parenttype": "User", "role": "System Manager"}):
        frappe.throw("Not permitted", frappe.PermissionError)
    name = frappe.form_dict.get("round") or ""
    if frappe.form_dict.get("action") == "queue":
        if frappe.db.exists("DD Request Details", name):
            from fieldpulse.customer_notifications import queue_event
            queue_event("details", frappe.get_doc("DD Request Details", name))
        return {"success": True}
    if not frappe.db.exists("DD Request Details", name):
        frappe.response["message"] = {"notification": None}
    else:
        detail = frappe.get_doc("DD Request Details", name)
        if frappe.form_dict.get("action") == "ack":
            frappe.db.set_value("DD Request Details", name, "email_sent_at", frappe.utils.now_datetime(), update_modified=False)
            frappe.response["message"] = {"success": True}
        else:
            request = frappe.get_doc("Diaspora Request", detail.request)
            account = frappe.get_doc("DD Customer Account", request.dd_customer_account)
            if detail.status != "Details needed" or detail.email_sent_at or not account.email_verified or not account.email_notifications or not frappe.db.get_value("User", account.user, "enabled"):
                frappe.response["message"] = {"notification": None}
            else:
                frappe.response["message"] = {"notification": {"email": account.user, "reference": request.name, "round": detail.name}}
    return frappe.response.pop("message", None)

@owned_event('DD Details Validation')
def validate(doc, method=None):
    previous = frappe.get_doc("DD Request Details", doc.name) if not doc.is_new() else None
    frappe.db.sql("SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE", [doc.request])
    request = frappe.get_doc("Diaspora Request", doc.request)
    if not request.dd_customer_account:
        frappe.throw("Details requests require a customer-linked request")
    if previous and previous.status != "Draft":
        if doc.request != previous.request or len(doc.questions) != len(previous.questions):
            frappe.throw("Published questions cannot be changed; create a new details request")
        for index in range(len(doc.questions)):
            question = doc.questions[index]
            original = previous.questions[index]
            changed = False
            for key in ["name", "question", "answer_type", "site_name"]:
                if question.get(key) != original.get(key): changed = True
            if changed:
                frappe.throw("Published questions cannot be changed")
            changed_answer = question.answer != original.answer or question.location_answer != original.location_answer
            if not doc.flags.get("dd_customer_response") and changed_answer:
                frappe.throw("Customer answers cannot be edited by staff")
        if doc.status != previous.status and not (previous.status == "Details needed" and doc.status == "Ready for review" and doc.flags.get("dd_customer_response")) and not (previous.status == "Ready for review" and doc.status == "Closed"):
            frappe.throw("Invalid details status transition")
        doc.published_at = previous.published_at
        doc.published_by = previous.published_by
        if not doc.flags.get("dd_customer_response"):
            doc.submitted_at = previous.submitted_at
            doc.submission_id = previous.submission_id
    if not previous or previous.status == "Draft":
        if doc.status not in ["Draft", "Details needed"]:
            frappe.throw("Publish questions before collecting answers")
        if not doc.questions or len(doc.questions) > 10:
            frappe.throw("Add between one and ten questions")
        for question in doc.questions:
            question.answer = None
            question.location_answer = None
            if not question.question or len(question.question) > 1000:
                frappe.throw("Enter a question of up to 1000 characters")
            if question.answer_type == "Location":
                matches = []
                for site in request.get("customer_sites") or []:
                    if site.name == question.site_name or site.site_label == question.site_name: matches.append(site)
                if len(matches) != 1:
                    frappe.throw("Select one existing site by its unique project label or row ID")
                question.site_name = matches[0].name
        if doc.status == "Details needed":
            if frappe.db.exists("DD Request Details", {"request": doc.request, "status": "Details needed", "name": ["!=", doc.name]}):
                frappe.throw("This request already has unanswered questions")
            doc.published_at = frappe.utils.now_datetime()
            doc.published_by = frappe.session.user

@owned_event('DD Details Next Action')
def update_next_action(doc, method=None):
    if doc.status == "Details needed":
        frappe.db.set_value("Diaspora Request", doc.request, {"customer_action_required": 1})
    elif doc.status == "Ready for review":
        frappe.db.set_value("Diaspora Request", doc.request, {"customer_action_required": 0})
