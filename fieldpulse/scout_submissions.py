"""Authoritative arrival, scope and review checks for revised questionnaires."""
import json
import frappe
from fieldpulse.scout_protocol import parsed, arrival_result, evaluate_submission


def assigned_questions(task):
    scope = parsed(task.get("questionnaire_scope"), []) or []
    rows = frappe.get_all("FP Question", filters={"questionnaire": task.questionnaire, "active": 1}, fields=["name", "question_code", "label", "question_type", "validation_json"], order_by="sequence asc")
    return [row for row in rows if row.question_code in scope] if scope else rows


def validate_submission(doc):
    task = frappe.get_doc("Field Task", doc.task)
    if not task.get("questionnaire_scope"): return False
    location = frappe.get_doc("FP Location", task.location) if task.location else {}
    raw = parsed(doc.get("arrival_check_json"), {}) or {}
    computed = arrival_result(raw, location)
    doc.geofence_status = "Invalid GPS" if computed["status"] == "Insufficient accuracy" else computed["status"]
    doc.geofence_distance_m = computed.get("distance_m")
    doc.arrival_check_json = json.dumps(dict(raw, **computed, task_id=task.name, scout_id=task.scout_profile))
    if doc.status != "Submitted": return True
    questions = assigned_questions(task)
    rows = frappe.get_all("FP Question Response", filters={"task_response": doc.name}, fields=["name", "question", "question_code", "answer_json"])
    by_question = {row.question: row for row in rows}
    answers, evidence = {}, {}
    for question in questions:
        row = by_question.get(question.name)
        if row:
            answers[question.question_code] = row.answer_json
            evidence[question.question_code] = frappe.get_all("Field Evidence", filters={"field_task": task.name, "question_response": row.name, "upload_status": "Uploaded"}, fields=["name", "evidence_type", "caption", "gps_lat", "gps_lng", "accuracy_m", "captured_at"])
    result = evaluate_submission(questions, answers, evidence, doc.get("final_review_json"), dict(raw, **computed), location=location)
    if result["errors"]: frappe.throw("; ".join(result["errors"]))
    doc.review_status = result["status"]
    doc.review_reasons = "\n".join(result["reasons"])
    doc.qa_status = "Needs Review" if result["reasons"] else "Pending"
    frappe.db.set_value("Field Task", task.name, {"submission_review_status": doc.review_status, "submission_review_reasons": doc.review_reasons}, update_modified=False)
    return True


def require_reviewer():
    if not {"System Manager", "Field Operations Coordinator"}.intersection(frappe.get_roles()):
        frappe.throw("Only coordinators may review scout submissions", frappe.PermissionError)


@frappe.whitelist()
def submission_detail(response):
    require_reviewer()
    doc = frappe.get_doc("FP Task Response", response)
    task = frappe.get_doc("Field Task", doc.task)
    answers = frappe.get_all("FP Question Response", filters={"task_response": doc.name}, fields=["name", "question", "question_code", "answer_json", "answer_text"])
    evidence = frappe.get_all("Field Evidence", filters={"question_response": ["in", [row.name for row in answers]], "field_task": task.name, "upload_status": "Uploaded"}, fields=["name", "question_response", "evidence_type", "caption", "captured_at", "gps_lat", "gps_lng", "accuracy_m"] ) if answers else []
    for item in evidence:
        site = frappe.get_doc("FP Location", task.location) if task.location else {}
        item["location_check"] = arrival_result(dict(latitude=item.get("gps_lat"), longitude=item.get("gps_lng"), accuracy_m=item.get("accuracy_m"), captured_at=item.get("captured_at")), site)
    return dict(task=task.name, request=frappe.db.get_value("Field Request", task.field_request, "diaspora_request") if task.field_request else None,
        client_request=parsed(task.get("client_request_snapshot"), {}), arrival=parsed(doc.get("arrival_check_json"), {}),
        final_review=parsed(doc.get("final_review_json"), {}), questions=assigned_questions(task), answers=answers, evidence=evidence,
        review_status=doc.get("review_status"), review_reasons=doc.get("review_reasons"))


@frappe.whitelist(methods=["POST"])
def review_submission(response, decision, notes):
    require_reviewer()
    if decision not in {"Approve", "Request rework"} or not isinstance(notes, str) or not notes.strip():
        frappe.throw("Choose a review decision and record the comparison with the client's request")
    frappe.db.sql("SELECT name FROM `tabFP Task Response` WHERE name=%s FOR UPDATE", [response])
    doc = frappe.get_doc("FP Task Response", response)
    frappe.db.sql("SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE", [doc.task])
    task = frappe.get_doc("Field Task", doc.task)
    if doc.status != "Submitted" or task.status != "Submitted": frappe.throw("Review an outstanding submitted response")
    doc.review_notes = notes.strip()
    doc.reviewed_by = frappe.session.user
    doc.reviewed_at = frappe.utils.now_datetime()
    doc.qa_status = "Passed" if decision == "Approve" else "Failed"
    # Keep the original submission and its review reasons; never silently repair scout answers.
    frappe.db.set_value("FP Task Response", doc.name, {key: doc.get(key) for key in ["review_notes", "reviewed_by", "reviewed_at", "qa_status"]})
    task.status = "Approved" if decision == "Approve" else "Rejected"
    task.submission_review_reasons = (doc.get("review_reasons") or "") + "\nCoordinator: " + notes.strip()
    task.submission_review_status = "Approved by coordinator" if decision == "Approve" else "Rework requested"
    task.save(ignore_permissions=True)
    return {"task": task.name, "status": task.status}
