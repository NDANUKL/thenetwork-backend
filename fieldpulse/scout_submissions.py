"""Authoritative arrival, scope and review checks for revised questionnaires."""
import json
import frappe
from fieldpulse.scout_protocol import parsed, arrival_result


def assigned_questions(task):
    scope = parsed(task.get("questionnaire_scope"), []) or []
    rows = frappe.get_all("FP Question", filters={"questionnaire": task.questionnaire, "active": 1}, fields=["name", "question_code", "label", "question_type", "validation_json"], order_by="sequence asc")
    from fieldpulse.scout_v2 import task_questions
    pinned = task_questions(task, None)
    if pinned: return [frappe._dict(row) for row in pinned]
    return [row for row in rows if row.question_code in scope] if scope else rows


def validate_submission(doc):
    task = frappe.get_doc("Field Task", doc.task)
    if task.get('task_brief_version'):
        from fieldpulse.task_brief_workflow import validate_response
        return validate_response(doc, task)
    frappe.throw('Historical questionnaire submissions are read-only. Use a Task Brief.')


def require_reviewer():
    if not {"System Manager", "Field Operations Coordinator"}.intersection(frappe.get_roles()):
        frappe.throw("Only coordinators may review scout submissions", frappe.PermissionError)


@frappe.whitelist()
def submission_detail(response):
    require_reviewer()
    doc = frappe.get_doc("FP Task Response", response)
    task = frappe.get_doc("Field Task", doc.task)
    if task.get('task_brief_version'):
        from fieldpulse.task_brief_workflow import submission_detail as brief_detail
        return brief_detail(doc, task)
    answers = frappe.get_all("FP Question Response", filters={"task_response": doc.name}, fields=["name", "question", "question_code", "answer_json", "answer_text"])
    evidence = frappe.get_all("Field Evidence", filters={"question_response": ["in", [row.name for row in answers]], "field_task": task.name, "upload_status": "Uploaded"}, fields=["name", "question_response", "evidence_type", "caption", "captured_at", "gps_lat", "gps_lng", "accuracy_m"] ) if answers else []
    questions = assigned_questions(task)
    summary = []
    from fieldpulse.scout_visit import strict, snapshot
    visit = strict(task)
    review_site = snapshot(task).get('site_reference') if visit else (frappe.get_doc('FP Location', task.location) if task.location else {})
    if questions and parsed(questions[0].validation_json, {}).get('protocol_version') == 2:
        from fieldpulse.scout_v2 import linked_evidence
        from fieldpulse.scout_library import evaluate
        evidence = [item for answer in answers for item in linked_evidence(doc.name, answer.name)]
        by_code = {answer.question_code: parsed(answer.answer_json, {}) for answer in answers}
        by_evidence = {answer.question_code: [item for item in evidence if item['question_response'] == answer.name] for answer in answers}
        summary = evaluate(questions, by_code, by_evidence, parsed(doc.get('arrival_check_json'), {}), review_site, parsed(doc.get('final_review_json'), {}))['summary']
    for item in evidence:
        item["location_check"] = arrival_result(dict(latitude=item.get("gps_lat"), longitude=item.get("gps_lng"), accuracy_m=item.get("accuracy_m"), captured_at=item.get("captured_at")), review_site or {}, strict=visit)
    return dict(task=task.name, request=frappe.db.get_value("Field Request", task.field_request, "diaspora_request") if task.field_request else None,
        client_request=parsed(task.get("client_request_snapshot"), {}), arrival=parsed(doc.get("arrival_check_json"), {}),
        final_review=parsed(doc.get("final_review_json"), {}), questions=questions, answers=answers, evidence=evidence, summary=summary,
        review_status=doc.get("review_status"), review_reasons=doc.get("review_reasons"))
