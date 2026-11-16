"""Durable post-submission brief jobs; AI runs only in the website's QStash worker."""
import json
import uuid
from datetime import timedelta

import frappe
from fieldpulse.task_briefs import validate_brief


def initialise(doc):
    # Only the new explicitly versioned portal flow opts into deferred generation.
    assessment = json.loads(doc.get('submitted_assessment') or '{}')
    if assessment.get('brief_generation_mode') != 'after_submission_v1':
        return
    details = json.loads(doc.get('project_details') or '[]')
    doc.task_brief_jobs = json.dumps({item['id']: {'status': 'Pending', 'attempts': 0}
        for item in details if item.get('eligibility') == 'supported' and not item.get('task_brief')})
    doc.task_brief_generation_status = 'Preparing' if json.loads(doc.task_brief_jobs) else 'Ready'


def require_service():
    if frappe.session.user == 'Guest' or 'System Manager' not in frappe.get_roles():
        frappe.throw('Only the trusted generation service may access these jobs', frappe.PermissionError)


@frappe.whitelist(methods=['POST'])
def capabilities():
    require_service()
    meta = frappe.get_meta('Diaspora Request')
    if not meta.has_field('task_brief_jobs') or not meta.has_field('task_brief_generation_status'):
        frappe.throw('Task Brief background schema migration is required')
    return {'contract': 'after_submission_v1'}


def locked_source(name):
    frappe.db.sql('SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE', [name])
    return frappe.get_doc('Diaspora Request', name)


def save_jobs(source, jobs):
    states = {job['status'] for job in jobs.values()}
    status = 'Preparing' if states.intersection({'Pending', 'Processing'}) else 'Needs attention' if 'Failed' in states else 'Ready'
    frappe.db.set_value('Diaspora Request', source.name, {'task_brief_jobs': json.dumps(jobs),
        'task_brief_generation_status': status}, update_modified=False)


@frappe.whitelist(methods=['POST'])
def pending(request_name=None):
    require_service()
    rows = frappe.get_all('Diaspora Request', filters={'task_brief_generation_status': 'Preparing',
        **({'name': request_name} if request_name else {})}, fields=['name', 'task_brief_jobs'],
        order_by='creation asc', limit_page_length=100)
    result = []
    for row in rows:
        for project_id, job in json.loads(row.task_brief_jobs or '{}').items():
            stale = job.get('lease_until') and frappe.utils.get_datetime(job['lease_until']) <= frappe.utils.now_datetime()
            if job['status'] == 'Pending' or (job['status'] == 'Processing' and stale):
                result.append({'request_name': row.name, 'project_id': project_id})
    return result


@frappe.whitelist(methods=['POST'])
def claim(request_name, project_id):
    require_service()
    source = locked_source(request_name)
    jobs = json.loads(source.get('task_brief_jobs') or '{}')
    job = jobs.get(project_id)
    if not job or job['status'] in {'Ready', 'Failed'}:
        return {'skip': True}
    if job['status'] == 'Processing' and frappe.utils.get_datetime(job['lease_until']) > frappe.utils.now_datetime():
        return {'busy': True}
    if job.get('attempts', 0) >= 3:
        job.update(status='Failed', error='Automatic generation attempts exhausted. Coordinator review required.')
        save_jobs(source, jobs)
        return {'skip': True}
    token = str(uuid.uuid4())
    job.update(status='Processing', token=token, attempts=job.get('attempts', 0) + 1,
        lease_until=str(frappe.utils.now_datetime() + timedelta(minutes=6)))
    save_jobs(source, jobs)
    details = json.loads(source.project_details or '[]')
    project = next(item for item in details if item['id'] == project_id)
    return {'token': token, 'project': project,
        'assessment': json.loads(source.submitted_assessment or '{}')}


@frappe.whitelist(methods=['POST'])
def complete(request_name, project_id, token, brief=None, error=None):
    require_service()
    source = locked_source(request_name)
    jobs = json.loads(source.get('task_brief_jobs') or '{}')
    job = jobs.get(project_id)
    if not job or job.get('token') != token or job['status'] != 'Processing':
        return {'stale': True}
    if error:
        job.update(status='Failed' if job['attempts'] >= 3 else 'Pending', error='Task Brief generation failed; retry or coordinator review required.')
        save_jobs(source, jobs)
        return {'saved': True}
    content = validate_brief(brief)
    details = json.loads(source.project_details or '[]')
    item = next(item for item in details if item['id'] == project_id)
    if item.get('eligibility') != 'supported' or content['category'] != item.get('service_category'):
        frappe.throw('Generated brief does not match the submitted project')
    # Immutable submission_snapshot and submitted_assessment retain their original provenance.
    item['task_brief'] = content
    frappe.db.set_value('Diaspora Request', source.name, 'project_details', json.dumps(details), update_modified=False)
    from fieldpulse.task_brief_workflow import seed_project_brief
    from fieldpulse.task_brief_revision_guard import lock_project
    for row in frappe.get_all('Field Request', filters={'diaspora_request': source.name, 'project_id': project_id}, fields=['name']):
        lock_project(row.name)
        seed_project_brief(frappe.get_doc('Field Request', row.name))
    job.update(status='Ready', error=None)
    save_jobs(source, jobs)
    return {'saved': True}


def project_status(project):
    source_name = project.get('diaspora_request')
    if not source_name:
        return None
    raw = frappe.db.get_value('Diaspora Request', source_name, 'task_brief_jobs')
    return json.loads(raw or '{}').get(project.get('project_id'))


@frappe.whitelist(methods=['POST'])
def coordinator_status(project, retry=False):
    if not {'System Manager', 'Field Operations Coordinator'}.intersection(frappe.get_roles()):
        frappe.throw('Only coordinators may access generation status', frappe.PermissionError)
    target = frappe.get_doc('Field Request', project)
    target.check_permission('write')
    if retry and str(retry) not in {'0', 'False', 'false'}:
        source = locked_source(target.diaspora_request)
        jobs = json.loads(source.get('task_brief_jobs') or '{}')
        job = jobs.get(target.project_id)
        if job and job['status'] == 'Failed':
            job.update(status='Pending', attempts=0, error=None)
            save_jobs(source, jobs)
    job = project_status(target)
    return {'status': job['status'], 'error': job.get('error')} if job else None
