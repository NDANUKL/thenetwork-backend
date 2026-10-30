"""Native Task Brief approval, dispatch and submission integration."""
import json
from datetime import timedelta

import frappe
from fieldpulse.task_briefs import CATEGORIES, validate_brief, brief_digest, assigned_brief, gps_result, evaluate_submission
from fieldpulse.mobile_datetime import mobile_datetime, site_datetime_iso
from fieldpulse.task_brief_revision_guard import lock_project, require_undispatched_project


def decoded(value, default=None):
    return json.loads(value) if isinstance(value, str) and value else value if value is not None else default


def prepare_project(doc, method=None):
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and previous.get('approved_task_brief') != doc.get('approved_task_brief'):
        require_undispatched_project(doc.name)
    if not doc.get('approved_task_brief'):
        return
    brief = frappe.get_doc('DD Task Brief', doc.approved_task_brief)
    if brief.project != doc.name or brief.status != 'Approved':
        frappe.throw('Select an approved Task Brief for this project')
    content = validate_brief(brief.content_json)
    doc.service_category = content['category']
    doc.request_type = CATEGORIES[content['category']]
    doc.alignment_review = int(not doc.get('county'))


def seed_project_brief(project):
    """Persist the initial request's generated draft once, never on mobile reads."""
    if not project.get('diaspora_request') or frappe.db.exists('DD Task Brief', {'project': project.name}):
        return
    source = frappe.get_doc('Diaspora Request', project.diaspora_request)
    details = decoded(source.get('project_details'), [])
    item = next((item for item in details if item.get('id') == project.get('project_id')), None)
    if not item or not item.get('task_brief'):
        return
    content = validate_brief(item['task_brief'])
    marker = frappe.flags.dd_initial_brief_project
    frappe.flags.dd_initial_brief_project = project.name
    try:
        frappe.get_doc(dict(doctype='DD Task Brief', project=project.name, status='Draft',
            content_json=json.dumps(content))).insert(ignore_permissions=True)
    finally:
        frappe.flags.dd_initial_brief_project = marker


@frappe.whitelist(methods=['POST'])
def open_project_brief(project):
    """Open this project's draft, recovering the original generated brief if needed."""
    if not {'System Manager', 'Field Operations Coordinator'}.intersection(frappe.get_roles()):
        frappe.throw('Only coordinators may prepare Task Briefs', frappe.PermissionError)
    request = frappe.get_doc('Field Request', project)
    request.check_permission('write')
    lock_project(project)
    drafts = frappe.get_list('DD Task Brief', filters={'project': project, 'status': 'Draft'},
                           fields=['name'], order_by='version desc', limit_page_length=1)
    if drafts:
        return drafts[0].name
    if request.get('approved_task_brief'):
        approved = frappe.get_doc('DD Task Brief', request.approved_task_brief)
        approved.check_permission('read')
        if approved.project != project or approved.status != 'Approved':
            frappe.throw('The selected Task Brief does not belong to this project')
        return approved.name
    require_undispatched_project(project)
    seed_project_brief(request)
    drafts = frappe.get_list('DD Task Brief', filters={'project': project, 'status': 'Draft'},
                           fields=['name'], order_by='version desc', limit_page_length=1)
    if drafts:
        return drafts[0].name
    # Historical/manual projects may have no initial AI output. Never invent checks.
    content = dict(schema_version=1, category=request.get('service_category') or 'custom_ground_verification',
        title=request.get('project_title') or project,
        objective=request.get('field_brief') or 'Review this project request',
        scope=request.get('field_brief') or 'Review this project request',
        instructions=[], deliverables=[], review_required=True,
        review_reasons=['No generated Task Brief is available for this project. Define its field checks before approval.'], checks=[])
    draft = frappe.get_doc(dict(doctype='DD Task Brief', project=project, status='Draft',
                               content_json=json.dumps(content)))
    draft.insert()
    return draft.name


def pin_assignment(task, method=None):
    if not task.is_new():
        return
    if not task.get('field_request'):
        frappe.throw('A Task Brief assignment must belong to a project')
    lock_project(task.field_request)
    project = frappe.get_doc('Field Request', task.field_request)
    reference = project.get('approved_task_brief')
    if not reference:
        frappe.throw('Review and approve the project Task Brief before assigning scouts')
    brief = frappe.get_doc('DD Task Brief', reference)
    if brief.project != project.name or brief.status != 'Approved':
        frappe.throw('The selected Task Brief is not approved for this project')
    content = validate_brief(brief.content_json)
    if brief_digest(content) != brief.content_hash or content['review_required']:
        frappe.throw('The approved Task Brief is inconsistent or requires review')
    check_ids = decoded(task.get('assigned_check_ids'), [])
    # Each allocation explicitly names its checks. Single-scout UI selects all.
    assigned_brief(content, check_ids)
    if not task.get('location'):
        frappe.throw('Confirm the project destination before assigning the Task Brief')
    location = frappe.get_doc('FP Location', task.location)
    site = dict(latitude=location.latitude, longitude=location.longitude,
                radius_m=location.get('geofence_radius_m') or 50,
                accuracy_threshold_m=project.get('gps_accuracy_threshold_m') or 20,
                label=location.get('location_name'), address=location.get('address'))
    sample = dict(latitude=site['latitude'], longitude=site['longitude'], accuracy_m=0,
                  captured_at='2000-01-01T00:00:00Z')
    if gps_result(sample, site)['status'] != 'inside':
        frappe.throw('The assignment needs valid destination coordinates and GPS tolerances')
    task.task_brief_version = brief.name
    task.assigned_check_ids = json.dumps(check_ids)
    task.task_brief_snapshot = json.dumps(dict(contract_version=1, brief=content,
        brief_id=brief.name, version=brief.version, content_hash=brief.content_hash,
        check_ids=check_ids, site=site), ensure_ascii=False)
    task.task_brief = content['objective']
    task.project_title = content['title']
    task.service_category = content['category']
    task.questionnaire = None
    task.questionnaire_scope = None
    task.questionnaire_version = 0


def validate_task(task, previous):
    if not previous or not previous.get('task_brief_version'):
        return
    for key in ('task_brief_version', 'task_brief_snapshot', 'assigned_check_ids', 'field_request', 'location', 'scout_profile'):
        if task.get(key) != previous.get(key):
            frappe.throw('Assigned briefs, checks, destination and scout are immutable; create a new allocation')
    if task.status == 'Approved' and previous.status != 'Approved':
        if not frappe.db.exists('FP Task Response', dict(task=task.name, status='Submitted', qa_status='Passed', reviewed_by=['is', 'set'])):
            frappe.throw('The coordinator must review and approve the scout submission first')


def snapshot(task):
    value = decoded(task.get('task_brief_snapshot'), {})
    if not value or value.get('contract_version') != 1:
        frappe.throw('This task does not have a pinned Task Brief')
    if value.get('content_hash') != brief_digest(value.get('brief')):
        frappe.throw('The pinned Task Brief is inconsistent')
    assigned_brief(value['brief'], value['check_ids'])
    # Owner-requested temporary cross-county test range; preserve GPS accuracy.
    from fieldpulse.geofence import effective_geofence_radius
    value['site']['radius_m'] = effective_geofence_radius(value['site']['radius_m'])
    return value


def evidence_records(response):
    rows = evidence_rows(response)
    return [dict(id=row.name, task_id=row.field_task, scout_id=row.scout, check_id=row.field_check_id,
                 kind=(row.evidence_type or '').lower(), source='camera' if row.metadata_origin == 'Camera' else 'gallery',
                 uploaded=True, file_id=row.r2_object_key, latitude=row.gps_lat, longitude=row.gps_lng,
                 accuracy_m=row.accuracy_m, captured_at=site_datetime_iso(row.captured_at),
                 location_sampled_at=site_datetime_iso(row.location_sampled_at)) for row in rows]


def evidence_rows(response):
    sources, current = [], response
    while current:
        if current.name in sources or current.task != response.task or current.agent != response.agent:
            frappe.throw('Invalid submission revision lineage')
        sources.append(current.name)
        if len(sources) > 50: frappe.throw('Too many submission revisions')
        current = frappe.get_doc('FP Task Response', current.rework_of) if current.get('rework_of') else None
    return frappe.get_all('Field Evidence', filters={'task_response': ['in', sources], 'upload_status': 'Uploaded'}, fields=['*'])


def submission_payload(doc):
    review = decoded(doc.get('final_review_json'), {})
    return dict(answers=decoded(doc.get('brief_answers_json'), {}), arrival=decoded(doc.get('arrival_check_json'), {}),
                declaration=review.get('declaration'), additional_observations=review.get('additional_observations', ''),
                **({'access_issue': review['access_issue']} if review.get('access_issue') is not None else {}))


def validate_response(doc, task):
    pinned = snapshot(task)
    payload = submission_payload(doc)
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and previous.get('arrival_check_json'):
        old = decoded(previous.arrival_check_json, {})
        if gps_result(old, pinned['site'])['status'] == 'inside' and old != payload['arrival']:
            frappe.throw('Keep the original verified arrival during this submission')
    arrival = payload['arrival']
    computed = gps_result(arrival, pinned['site'])
    doc.geofence_status = {'inside':'Inside','outside':'Outside','invalid':'Invalid GPS','inaccurate':'Invalid GPS'}[computed['status']]
    doc.geofence_distance_m = computed['distance_m']
    if arrival.get('captured_at'):
        captured = mobile_datetime(arrival['captured_at'])
        if not captured or captured < mobile_datetime(task.assigned_at) or captured > frappe.utils.now_datetime() + timedelta(minutes=5):
            frappe.throw('Arrival must be captured during this assignment')
    if payload['answers'] and gps_result(arrival, pinned['site'])['status'] != 'inside':
        frappe.throw('Verify arrival before saving field checks')
    if not isinstance(payload['answers'], dict) or set(payload['answers']) - set(pinned['check_ids']):
        frappe.throw('Answers must belong to this scout\'s assigned checks')
    if doc.status != 'Submitted':
        return True
    result = evaluate_submission(pinned['brief'], pinned['check_ids'], payload, evidence_records(doc),
        task_id=task.name, scout_id=task.scout_profile, site=pinned['site'])
    if not result['complete']:
        frappe.throw('; '.join(result['errors']))
    doc.review_status = 'Needs coordinator review'
    doc.review_reasons = '\n'.join(result['flags'])
    doc.qa_status = 'Pending'
    doc.brief_completion_json = json.dumps(result)
    return True


@frappe.whitelist(methods=['POST'])
def record_progress(task_name, brief_hash):
    """Idempotent mobile activity acknowledgement; never reopen closed work."""
    from fieldpulse.api import _get_scout_profile_for_user
    scout = _get_scout_profile_for_user()
    frappe.db.sql('SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE', [task_name])
    task = frappe.get_doc('Field Task', task_name)
    if task.scout_profile != scout.name:
        frappe.throw('This task belongs to another scout', frappe.PermissionError)
    if snapshot(task)['content_hash'] != brief_hash:
        frappe.throw('Sync the approved Task Brief before recording progress')
    if task.status == 'Assigned':
        task.status = 'Accepted'
        task.save(ignore_permissions=True)
    if task.status == 'Accepted':
        task.status = 'In Progress'
        task.save(ignore_permissions=True)
    return dict(status=task.status, started_at=task.get('started_at'))


@frappe.whitelist(methods=['POST'])
def save_response(payload):
    from fieldpulse.api import _get_scout_profile_for_user
    payload = decoded(payload, {})
    if not isinstance(payload, dict) or not isinstance(payload.get('client_uuid'), str) or not 1 <= len(payload['client_uuid']) <= 140:
        frappe.throw('A valid submission ID is required')
    scout = _get_scout_profile_for_user()
    frappe.db.sql('SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE', [payload.get('task')])
    task = frappe.get_doc('Field Task', payload.get('task'))
    if task.scout_profile != scout.name:
        frappe.throw('This task belongs to another scout', frappe.PermissionError)
    pinned = snapshot(task)
    if payload.get('brief_hash') != pinned['content_hash']:
        frappe.throw('Sync the approved Task Brief before submitting')
    existing = frappe.db.exists('FP Task Response', {'client_uuid': payload['client_uuid']})
    doc = frappe.get_doc('FP Task Response', existing) if existing else frappe.new_doc('FP Task Response')
    if existing and (doc.task != task.name or doc.agent != scout.name):
        frappe.throw('The submission ID belongs to another assignment', frappe.PermissionError)
    if existing and doc.status == 'Submitted':
        return dict(response=doc.name, status='Submitted', task_status=task.status)
    if payload.get('reconcile_only'):
        return dict(response=doc.name if existing else None, status=doc.status if existing else 'Missing', task_status=task.status)
    if task.status not in ('Assigned', 'Accepted', 'In Progress'):
        frappe.throw('This assignment is not open for submission')
    if not existing and frappe.db.exists('FP Task Response', {'task': task.name, 'status': 'Draft'}):
        frappe.throw('Resume the existing draft for this assignment')
    if payload.get('status') not in ('Draft', 'Submitted'):
        frappe.throw('Scouts may save a draft or submit for coordinator review')
    doc.client_uuid = payload['client_uuid']
    doc.task, doc.agent, doc.location = task.name, scout.name, task.location
    doc.status = payload['status']
    doc.client_updated_at = frappe.utils.now_datetime()
    if doc.status == 'Submitted':
        doc.submitted_at = frappe.utils.now_datetime()
    doc.arrival_check_json = json.dumps(payload.get('arrival') or {})
    doc.brief_answers_json = json.dumps(payload.get('answers') or {})
    doc.final_review_json = json.dumps({key: payload[key] for key in ('declaration', 'additional_observations', 'access_issue') if key in payload})
    doc.save(ignore_permissions=True)
    return dict(response=doc.name, status=doc.status)


def submission_detail(doc, task):
    pinned = snapshot(task)
    return dict(task=task.name, brief=pinned, submission=submission_payload(doc),
        completion=decoded(doc.get('brief_completion_json'), {}),
        evidence=evidence_rows(doc),
        review_status=doc.qa_status, review_notes=doc.get('review_notes'))


@frappe.whitelist(methods=['POST'])
def review_response(response, decision, notes):
    from fieldpulse.scout_submissions import require_reviewer
    require_reviewer()
    if decision not in ('Approve', 'Reject', 'Request clarification', 'Request additional evidence') or not isinstance(notes, str) or not notes.strip():
        frappe.throw('Choose a decision and record the review findings')
    task_name = frappe.db.get_value('FP Task Response', response, 'task')
    frappe.db.sql('SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE', [task_name])
    frappe.db.sql('SELECT name FROM `tabFP Task Response` WHERE name=%s FOR UPDATE', [response])
    doc = frappe.get_doc('FP Task Response', response)
    task = frappe.get_doc('Field Task', task_name)
    task.check_permission('write')
    if doc.status != 'Submitted' or task.status != 'Submitted' or doc.qa_status in ('Passed', 'Failed'):
        frappe.throw('Review an outstanding submitted assignment')
    pinned = snapshot(task)
    result = evaluate_submission(pinned['brief'], pinned['check_ids'], submission_payload(doc), evidence_records(doc),
        task_id=task.name, scout_id=task.scout_profile, site=pinned['site'])
    if decision == 'Approve' and (not result['complete'] or result['status'] == 'access_issue'):
        frappe.throw('An incomplete submission or access issue cannot approve fieldwork')
    frappe.db.set_value('FP Task Response', doc.name, dict(qa_status='Passed' if decision == 'Approve' else 'Failed',
        review_notes=notes.strip(), reviewed_by=frappe.session.user, reviewed_at=frappe.utils.now_datetime()))
    task.submission_review_reasons = notes.strip()
    task.submission_review_status = 'Approved by coordinator' if decision == 'Approve' else decision
    task.status = 'Approved' if decision == 'Approve' else 'Rejected' if decision == 'Request clarification' else 'Cancelled'
    if decision == 'Request clarification': task.rework_type = 'Correct answers'
    task.save(ignore_permissions=True)
    if decision == 'Request clarification':
        from uuid import uuid4
        identity = str(uuid4())
        marker = frappe.flags.dd_rework_response_uuid
        frappe.flags.dd_rework_response_uuid = identity
        try:
            revision = frappe.get_doc(dict(doctype='FP Task Response', client_uuid=identity, task=task.name,
                agent=task.scout_profile, location=task.location, status='Draft', rework_of=doc.name,
                rework_type='Correct answers', client_updated_at=frappe.utils.now_datetime(),
                arrival_check_json=doc.arrival_check_json, brief_answers_json=doc.brief_answers_json,
                final_review_json=json.dumps(dict(additional_observations=submission_payload(doc).get('additional_observations',''), declaration=False))))
            revision.insert(ignore_permissions=True)
        finally:
            frappe.flags.dd_rework_response_uuid = marker
        frappe.db.set_value('Field Task', task.name, 'rework_response', revision.name)
        from fieldpulse.scout_notifications import queue_rework
        queue_rework(task, doc, 'Correct answers',
            [check['instruction'] for check in pinned['brief']['checks'] if check['id'] in pinned['check_ids']], notes.strip())
    elif decision != 'Approve':
        frappe.db.set_value('Field Request', task.field_request, 'status', 'Awaiting Assignment')
    else:
        from fieldpulse.scout_reports import prepare_if_ready
        reference = frappe.db.get_value('Field Request', task.field_request, 'diaspora_request')
        if reference:
            prepare_if_ready(reference)
    return dict(task=task.name, status=task.status)


def revision_payload(task):
    if not task.get('rework_response'): return None
    response = frappe.get_doc('FP Task Response', task.rework_response)
    if response.status != 'Draft': return None
    return dict(id=response.client_uuid, server_id=response.name, submission=submission_payload(response),
        media=[dict(id=item.client_uuid, server_id=item.name, check_id=item.field_check_id,
                    kind=item.evidence_type.lower(), mime_type=item.mime_type, size_bytes=item.file_size,
                    captured_at=site_datetime_iso(item.captured_at), latitude=item.gps_lat, longitude=item.gps_lng,
                    accuracy_m=item.accuracy_m, location_sampled_at=site_datetime_iso(item.location_sampled_at),
                    metadata_origin='Camera', local_uri='') for item in evidence_rows(response)])


def coverage_ready(project_names):
    """A cancelled allocation must not silently remove required client checks."""
    for name in project_names:
        project = frappe.get_doc('Field Request', name)
        if not project.get('approved_task_brief'):
            continue
        approved = frappe.get_doc('DD Task Brief', project.approved_task_brief)
        required = {check['id'] for check in validate_brief(approved.content_json)['checks'] if check['required']}
        covered = set()
        for task in frappe.get_all('Field Task', filters={'field_request': name, 'status': 'Approved'}, fields=['task_brief_version', 'assigned_check_ids']):
            if task.task_brief_version == approved.name:
                covered.update(decoded(task.assigned_check_ids, []))
        if not required <= covered:
            return False
    return True
