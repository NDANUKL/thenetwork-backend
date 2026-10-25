"""Authoritative arrival, scope and review checks for revised questionnaires."""
import json
import frappe
from fieldpulse.scout_protocol import parsed, arrival_result, evaluate_submission


def assigned_questions(task):
    scope = parsed(task.get("questionnaire_scope"), []) or []
    rows = frappe.get_all("FP Question", filters={"questionnaire": task.questionnaire, "active": 1}, fields=["name", "question_code", "label", "question_type", "validation_json"], order_by="sequence asc")
    from fieldpulse.scout_v2 import task_questions
    pinned = task_questions(task, None)
    if pinned: return [frappe._dict(row) for row in pinned]
    return [row for row in rows if row.question_code in scope] if scope else rows


def validate_submission(doc):
    task = frappe.get_doc("Field Task", doc.task)
    if not task.get("questionnaire_scope"): return False
    location = frappe.get_doc("FP Location", task.location) if task.location else {}
    from fieldpulse.scout_visit import strict, snapshot
    visit = strict(task)
    if visit: location = snapshot(task).get('site_reference') or {}
    raw = parsed(doc.get("arrival_check_json"), {}) or {}
    if visit and not doc.is_new():
        previous = doc.get_doc_before_save()
        previous_arrival = parsed(previous.get('arrival_check_json'), {}) if previous else {}
        if previous and arrival_result(previous_arrival, location, strict=True)['status'] == 'Inside':
            for key in ('latitude','longitude','accuracy_m','captured_at'):
                if raw.get(key) != previous_arrival.get(key): frappe.throw('Keep the saved verified arrival; later writing/submission must not replace it')
    if doc.get('rework_type') == 'Return to site' and doc.get('rework_of') and raw.get('captured_at'):
        from fieldpulse.scout_rework import require_fresh_capture
        require_fresh_capture(doc, raw.get('captured_at'))
    computed = arrival_result(raw, location, strict=visit)
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
            if parsed(question.validation_json, {}).get('protocol_version') == 2:
                from fieldpulse.scout_v2 import linked_evidence
                evidence[question.question_code] = linked_evidence(doc.name, row.name)
            else:
                evidence[question.question_code] = frappe.get_all("Field Evidence", filters={"field_task": task.name, "question_response": row.name, "upload_status": "Uploaded"}, fields=["name", "evidence_type", "caption", "gps_lat", "gps_lng", "accuracy_m", "captured_at"])
    if questions and parsed(questions[0].validation_json, {}).get('protocol_version') == 2:
        from fieldpulse.scout_library import evaluate
        result = evaluate(questions, {code: parsed(value, {}) for code, value in answers.items()}, evidence, dict(raw, **computed), location, parsed(doc.get('final_review_json'), {}))
    else:
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


@frappe.whitelist(methods=["POST"])
def review_submission(response, decision, notes, rework_type=None, rework_questions=None, rework_assignment='Same scout', replacement_scout=None, reassignment_reason=None):
    require_reviewer()
    if decision not in {"Approve", "Request rework"} or not isinstance(notes, str) or not notes.strip():
        frappe.throw("Choose a review decision and record the comparison with the client's request")
    # Serialize reviews for a request before locking individual responses/tasks.
    task_name = frappe.db.get_value('FP Task Response', response, 'task')
    project = frappe.db.get_value('Field Task', task_name, 'field_request')
    reference = frappe.db.get_value('Field Request', project, 'diaspora_request') if project else None
    if reference: frappe.db.sql('SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE', [reference])
    frappe.db.sql("SELECT name FROM `tabFP Task Response` WHERE name=%s FOR UPDATE", [response])
    doc = frappe.get_doc("FP Task Response", response)
    if decision == 'Approve' and parsed(doc.get('final_review_json'), {}).get('visit_route') == 'arrival_exception':
        frappe.throw('An arrival exception cannot approve fieldwork. Correct the site/access issue and request rework.')
    frappe.db.sql("SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE", [doc.task])
    task = frappe.get_doc("Field Task", doc.task)
    if doc.status != "Submitted" or task.status != "Submitted" or doc.qa_status in ('Passed', 'Failed'): frappe.throw("Review an outstanding submitted response")
    codes = []
    selected_scout = None
    if decision == 'Request rework':
        from fieldpulse.scout_rework import validate_request
        codes = validate_request(doc, task, rework_type, rework_questions)
        from fieldpulse.scout_rework import validate_assignment
        selected_scout = validate_assignment(task, rework_type, rework_assignment, replacement_scout, reassignment_reason)
    if decision == 'Approve':
        detail = submission_detail(doc.name)
        from fieldpulse.customer_coverage import required_review_errors
        errors = required_review_errors(detail)
        if errors: frappe.throw('Complete required answers/evidence before approval: ' + '; '.join(errors))
    doc.review_notes = notes.strip()
    doc.reviewed_by = frappe.session.user
    doc.reviewed_at = frappe.utils.now_datetime()
    doc.qa_status = "Passed" if decision == "Approve" else "Failed"
    # Keep the original submission and its review reasons; never silently repair scout answers.
    frappe.db.set_value("FP Task Response", doc.name, {key: doc.get(key) for key in ["review_notes", "reviewed_by", "reviewed_at", "qa_status"]})
    revisit = decision == 'Request rework' and rework_type == 'Return to site'
    task.status = 'Awaiting authorization' if revisit else "Approved" if decision == "Approve" else "Rejected"
    task.submission_review_reasons = (doc.get("review_reasons") or "") + "\nCoordinator: " + notes.strip()
    task.submission_review_status = "Approved by coordinator" if decision == "Approve" else "Rework requested"
    if decision == 'Request rework':
        task.rework_type = rework_type
        task.rework_questions_json = json.dumps(codes)
        frappe.db.set_value('FP Task Response', doc.name, {'rework_questions_json': json.dumps(codes)})
    marker = frappe.flags.dd_pending_revisit_response
    if revisit: frappe.flags.dd_pending_revisit_response = doc.name
    try: task.save(ignore_permissions=True)
    finally: frappe.flags.dd_pending_revisit_response = marker
    report = None
    revisit_request = None
    if decision == 'Request rework':
        if revisit:
            from fieldpulse.revisit_authorization import create_request
            revisit_request = create_request(task, doc, reference, codes, notes, rework_assignment, selected_scout, reassignment_reason)
        else:
            from fieldpulse.scout_rework import create_revision
            revision = create_revision(doc, task, rework_type)
            frappe.db.set_value('Field Task', task.name, 'rework_response', revision.name)
            from fieldpulse.scout_notifications import queue_rework
            queue_rework(task, doc, rework_type, codes, notes.strip())
    elif reference:
        from fieldpulse.scout_reports import prepare_if_ready
        report = prepare_if_ready(reference)
    return {"task": task.name, "status": task.status, "report": report, "replacement_task": None, "revisit_request": revisit_request}
