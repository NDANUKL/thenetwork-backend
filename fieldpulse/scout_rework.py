"""Server-owned response revisions. Originals and capture provenance stay intact."""
import copy
import json
from uuid import uuid4
import frappe
from fieldpulse.scout_protocol import parsed

TYPES = {'Correct answers', 'Return to site'}


def validate_assignment(task, kind, choice='Same scout', scout=None, reason=None):
    if choice not in ('Same scout', 'Assign another scout'):
        frappe.throw('Choose Same scout or Assign another scout')
    if choice == 'Same scout':
        if scout or reason:
            frappe.throw('A replacement scout and reassignment reason require Assign another scout')
        return None
    if kind != 'Return to site':
        frappe.throw('Answer corrections must stay with the original scout')
    if not isinstance(reason, str) or not reason.strip():
        frappe.throw('Explain why the revisit is being assigned to another scout')
    if not scout or scout == task.scout_profile:
        frappe.throw('Choose a different scout for the new revisit assignment')
    if not task.get('field_request') or not frappe.has_permission('Field Task', 'create'):
        frappe.throw('Not permitted to create a replacement assignment', frappe.PermissionError)
    frappe.get_doc('Field Request', task.field_request).check_permission('write')
    frappe.db.sql('SELECT name FROM `tabScout Profile` WHERE name=%s FOR UPDATE', [scout])
    profile = frappe.get_doc('Scout Profile', scout)
    profile.check_permission('read')
    if profile.availability_status == 'On Leave' or not profile.user or not frappe.db.get_value('User', profile.user, 'enabled'):
        frappe.throw('Choose an available scout with an enabled user account')
    if frappe.db.exists('Field Task', {'field_request': task.field_request, 'scout_profile': scout, 'status': ['not in', ['Cancelled', 'Approved']]}):
        frappe.throw('This scout already has an active assignment for the project')
    return profile.name


def create_replacement(task, source, scout, reason, codes, notes):
    """Preserve ownership of the original task; dispatch independent fieldwork."""
    values = {key: task.get(key) for key in ('field_request', 'location', 'questionnaire',
        'questionnaire_version', 'questionnaire_scope', 'client_request_snapshot', 'due_at', 'priority')}
    values.update(doctype='Field Task', scout_profile=scout, status='Assigned',
        replaces_task=task.name, rework_source_response=source.name,
        rework_assignment_reason=reason.strip(), rework_type='Return to site',
        rework_questions_json=json.dumps(codes), rework_count=0,
        submission_review_status='Revisit assigned', submission_review_reasons=notes.strip())
    replacement = frappe.get_doc(values)
    previous_marker = frappe.flags.dd_replacement_source
    frappe.flags.dd_replacement_source = task.name
    try:
        replacement.insert(ignore_permissions=True)
    finally:
        frappe.flags.dd_replacement_source = previous_marker
    revision = create_revision(source, replacement, 'Return to site')
    frappe.db.set_value('Field Task', replacement.name, 'rework_response', revision.name)
    replacement.rework_response = revision.name
    task.replacement_task = replacement.name
    task.rework_assignment_reason = reason.strip()
    task.submission_review_status = 'Rework reassigned'
    task.submission_review_reasons = 'Revisit assigned to another scout. ' + reason.strip()
    task.append('reassignment_history', dict(from_scout=task.scout_profile, to_scout=scout,
        reassigned_by=frappe.session.user, reassigned_at=frappe.utils.now_datetime(), reason=reason.strip()))
    task.status = 'Cancelled'
    task.save(ignore_permissions=True)
    old_user = frappe.db.get_value('Scout Profile', task.scout_profile, 'user')
    if old_user:
        frappe.get_doc(dict(doctype='Notification Log', for_user=old_user, from_user=frappe.session.user,
            type='Alert', subject='Your assignment has ended - ' + (task.get('task_number') or task.name),
            document_type='Field Task', document_name=task.name)).insert(ignore_permissions=True)
    return replacement


def require_fresh_capture(response, captured_at):
    if response.get('rework_type') != 'Return to site' or not response.get('rework_of'):
        return
    from fieldpulse.mobile_datetime import mobile_datetime
    requested_at = frappe.db.get_value('FP Task Response', response.rework_of, 'reviewed_at')
    if response.get('task'):
        revisit = frappe.db.get_value('Field Task', response.task, 'revisit_request')
        if revisit:
            authorization = frappe.get_doc('DD Revisit Request', revisit)
            if authorization.status != 'Dispatched' or authorization.dispatched_task != response.task:
                frappe.throw('Authorize and dispatch the revisit before recording fieldwork')
            requested_at = authorization.dispatched_at

    captured = mobile_datetime(captured_at)
    if not captured or not requested_at or captured <= mobile_datetime(requested_at):
        frappe.throw('A site revisit requires evidence captured after the rework request and authorized dispatch')


def validate_request(doc, task, kind, questions):
    from fieldpulse.scout_submissions import assigned_questions
    if kind not in TYPES:
        frappe.throw('Choose Correct answers or Return to site')
    codes = parsed(questions, [])
    valid = {q.question_code for q in assigned_questions(task)}
    if not isinstance(codes, list) or not codes or any(not isinstance(c, str) or c not in valid for c in codes):
        frappe.throw('Select the assigned questions that need rework')
    if kind == 'Correct answers':
        if (parsed(task.get('client_request_snapshot'), {}) or {}).get('protocol_version') != 2:
            frappe.throw('Answer corrections require a version 2 questionnaire; use Return to site for this older assignment')
        from fieldpulse.scout_visit import strict, verified_arrival
        if (parsed(doc.get('final_review_json'), {}) or {}).get('visit_route') == 'arrival_exception' or (strict(task) and verified_arrival(doc, task)['status'] != 'Inside'):
            frappe.throw('Unverified fieldwork requires Return to site')
    return list(dict.fromkeys(codes))


def create_revision(source, task, kind):
    correction = kind == 'Correct answers'
    if correction and (source.task != task.name or source.agent != task.scout_profile):
        frappe.throw('Answer corrections must stay with the original scout and task')
    values = dict(doctype='FP Task Response', client_uuid=str(uuid4()), task=task.name,
        agent=task.scout_profile, location=task.get('location') or source.location, status='Draft', qa_status='Pending',
        client_updated_at=source.get('client_updated_at') or frappe.utils.now_datetime(), rework_of=source.name, rework_type=kind)
    if correction:
        for key in ('arrival_check_json', 'started_at', 'latitude', 'longitude', 'accuracy_m'):
            values[key] = source.get(key)
        final = parsed(source.get('final_review_json'), {}) or {}
        final.pop('visit_route', None)
        final['work_phase'] = 'findings'
        values['final_review_json'] = json.dumps(final)
    revision = frappe.get_doc(values)
    revision.flags.server_rework = True
    previous_marker = frappe.flags.dd_rework_response_uuid
    frappe.flags.dd_rework_response_uuid = revision.client_uuid
    try:
        revision.insert(ignore_permissions=True)
    finally:
        frappe.flags.dd_rework_response_uuid = previous_marker
    if correction:
        for row in frappe.get_all('FP Question Response', filters={'task_response': source.name}, pluck='name'):
            original = frappe.get_doc('FP Question Response', row)
            answer = frappe.get_doc(dict(doctype='FP Question Response', client_uuid=str(uuid4()),
                task_response=revision.name, question=original.question, question_type=original.question_type,
                question_code=original.question_code, answer_json=original.answer_json,
                answer_text=original.answer_text, client_updated_at=original.get('client_updated_at') or source.get('client_updated_at') or frappe.utils.now_datetime()))
            answer.set('evidence_links', [{key: link.get(key) for key in ('evidence', 'requirement_id', 'support_note')} for link in original.get('evidence_links') or []])
            answer.insert(ignore_permissions=True)
    return revision


def revision_payload(task):
    name = task.get('rework_response')
    if not name or task.status in ('Approved', 'Cancelled'):
        return None
    doc = frappe.get_doc('FP Task Response', name)
    if doc.task != task.name or doc.agent != task.scout_profile or doc.status != 'Draft':
        return None
    answers = frappe.get_all('FP Question Response', filters={'task_response': name},
        fields=['name', 'client_uuid', 'question', 'answer_json'])
    files = {}
    for row in answers:
        answer = copy.deepcopy(parsed(row.answer_json, {}) or {})
        links = []
        for link in frappe.get_all('DD Answer Evidence Link', filters={'parent': row.name, 'parenttype': 'FP Question Response'}, fields=['evidence', 'requirement_id', 'support_note']):
            evidence = frappe.get_doc('Field Evidence', link.evidence)
            links.append(dict(attachment_id=evidence.client_uuid, requirement_id=link.requirement_id, support_note=link.support_note))
            files.setdefault(evidence.client_uuid, dict(id=evidence.client_uuid, server_id=evidence.name, question_id=row.question,
                mime_type=evidence.mime_type, evidence_type=evidence.evidence_type, caption=evidence.caption,
                captured_at=str(evidence.captured_at) if evidence.captured_at else None,
                latitude=evidence.gps_lat, longitude=evidence.gps_lng, accuracy_m=evidence.accuracy_m,
                metadata_origin=evidence.get('metadata_origin'), location_sampled_at=str(evidence.location_sampled_at) if evidence.get('location_sampled_at') else None,
                description=evidence.get('description'), clarification_required=evidence.get('clarification_required'), subjects=[]))
            files[evidence.client_uuid]['subjects'].append(link.requirement_id)
        if isinstance(answer, dict):
            # Never use client-supplied media metadata as capture provenance.
            answer['media'] = []
            answer['evidence_links'] = links
        row['answer_json'] = json.dumps(answer)
    for row in answers:
        answer = parsed(row.answer_json, {}) or {}
        if isinstance(answer, dict):
            ids = {link['attachment_id'] for link in answer.get('evidence_links', [])}
            answer['media'] = [dict(file, inherited=True, attachment_id=file['id'], kind=file['evidence_type']) for file in files.values() if file['id'] in ids and file['question_id'] == row.question]
            row['answer_json'] = json.dumps(answer)
    return dict(name=doc.name, client_uuid=doc.client_uuid, arrival_check_json=doc.arrival_check_json,
        final_review_json=doc.final_review_json, answers=answers, files=list(files.values()))
