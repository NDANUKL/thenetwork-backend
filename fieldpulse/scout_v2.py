"""Version 2 installation, dispatch snapshots and verified evidence associations."""
import copy
import hashlib
import json
from pathlib import Path
import frappe
from fieldpulse.school_fees import apply_policy
from fieldpulse.scout_library import (SHARED_V2, CLOSING_V2, decode, resolve_config,
    validate_config, required_evidence, visible)


def catalogue():
    version = 3 if workflow_enabled() else 2
    return apply_policy(json.loads((Path(__file__).parent / f'configuration/scout-questionnaires-v{version}.json').read_text(encoding='utf-8')))


def workflow_enabled():
    return bool(getattr(frappe, 'conf', {}).get('dd_scout_visit_workflow_enabled'))


def enabled():
    return bool(getattr(frappe, 'conf', {}).get('dd_questionnaire_v2_enabled'))


@frappe.whitelist()
def library_options():
    from fieldpulse.scout_submissions import require_reviewer
    require_reviewer()
    return dict(enabled=enabled(), services=[dict(code=s['service_code'], title=s['title']) for s in catalogue()['services']])


def install_templates(preserve_published=False):
    """Opt-in installation only; never changes existing project/task pins."""
    if not enabled(): return
    for service in catalogue()['services']: install_service([service], preserve_published=preserve_published)


def install_service(services, preserve_published=False):
    data = catalogue()
    combined = len(services) > 1
    identity_data = dict(services=services, shared=SHARED_V2, closing=CLOSING_V2, source_sha256=data['source_sha256'])
    if data.get('visit_workflow_version'): identity_data.update(visit_workflow_version=data['visit_workflow_version'], policy_sha256=data['policy_sha256'])
    identity = hashlib.sha256(json.dumps(identity_data, sort_keys=True).encode()).hexdigest()
    code = 'DD-bundle-' + identity[:16] if combined else 'DD-' + services[0]['service_code']
    version = max([data['version']] + [s.get('questionnaire_version', data['version']) for s in services])
    name = code + '-v' + str(version)
    if frappe.db.exists('FP Questionnaire', name):
        if frappe.db.get_value('FP Questionnaire', name, 'schema_hash') != identity:
            if preserve_published:
                from fieldpulse.scout_templates import preserve_existing_published
                if preserve_existing_published(name, preserve_published): return name
            frappe.throw('Publish a new version; questionnaire source changed')
        return name
    doc = frappe.get_doc(dict(doctype='FP Questionnaire', questionnaire_code=code,
        title=' / '.join(s['title'] for s in services), service_code=services[0]['service_code'],
        version=version, status='Draft', description='\n\n'.join(s['description'] for s in services),
        schema_hash=identity, source_sha256=data['source_sha256']))
    doc.insert(ignore_permissions=True, set_name=name)
    rows = [dict(q, group='shared') for q in SHARED_V2]
    for service in services:
        rows += [dict(q, group='service', service=service['service_code'], authorisation_required=service.get('authorisation_required', False)) for q in service['questions']]
    rows.append(dict(CLOSING_V2, group='final'))
    for sequence, row in enumerate(rows, 1):
        config = dict(row, protocol_version=2)
        if data.get('visit_workflow_version'): config['visit_workflow_version'] = data['visit_workflow_version']
        validate_config(config)
        frappe.get_doc(dict(doctype='FP Question', questionnaire=name, question_code=row['code'],
            label=row['label'], help_text=row.get('detail', ''), question_type='service_check',
            sequence=sequence, required=int(row['group'] != 'final'), active=1,
            question_group={'shared':'Shared', 'service':'Service', 'final':'Final review'}[row['group']],
            validation_json=json.dumps(config))).insert(ignore_permissions=True)
    doc.status = 'Published'
    doc.published_at = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    return name


@frappe.whitelist(methods=['POST'])
def select_services(project, services):
    from fieldpulse.scout_submissions import require_reviewer
    require_reviewer()
    if not enabled(): frappe.throw('Enable dd_questionnaire_v2_enabled after staging and compatible mobile rollout')
    doc = frappe.get_doc('Field Request', project)
    doc.check_permission('write')
    if frappe.db.exists('Field Task', {'field_request': doc.name, 'status': ['not in', ['Cancelled', 'Approved']]}):
        frappe.throw('Finish or cancel existing assignments before changing the site service bundle')
    codes = decode(services, [])
    known = {s['service_code']: s for s in catalogue()['services']}
    if not codes or len(set(codes)) != len(codes) or not set(codes) <= set(known): frappe.throw('Choose unique services from the library')
    selected = [known[code] for code in codes]
    doc.scout_service = selected[0]['title']
    doc.scout_questionnaire = install_service(selected)
    doc.set('scout_checks', [])
    doc.scout_checks_confirmed = 0
    doc.save()
    return doc.scout_questionnaire


def resolved_questions(project, questions):
    selected = {row.question: row for row in project.get('scout_checks') or [] if row.get('question')}
    rows = []
    for question in questions:
        config = decode(question.validation_json, {})
        if config.get('protocol_version') != 2: continue
        if config['group'] == 'service' and question.name not in selected: continue
        assignment = selected[question.name].get('configuration_json') if question.name in selected else None
        resolved = resolve_config(config, assignment)
        if resolved is None: continue
        if resolved.get('previous_required') and not project.get('scout_reference_material'):
            raise ValueError('Supply the previous report/reference material for a progress comparison')
        if resolved.get('authorisation_required') and not str(project.get('scout_authorisation') or '').strip():
            raise ValueError('Record required authorisation and institutional arrangements before assignment')
        rows.append(dict(name=question.name, question_code=question.question_code,
            label=question.label, help_text=question.get('help_text', ''), question_type='service_check',
            required=config['group'] != 'final', validation_json=json.dumps(resolved)))
    if not any(decode(q['validation_json'])['group'] == 'service' for q in rows): raise ValueError('Assign at least one service check')
    return rows


def snapshot_context(project):
    return {key: project.get(field) for key, field in {
        'reference_material':'scout_reference_material', 'contact_access':'scout_contact_access',
        'authorisation':'scout_authorisation', 'restrictions':'scout_restrictions',
    }.items()}


def task_questions(task, fallback):
    snapshot = decode(task.get('client_request_snapshot'), {})
    return snapshot.get('resolved_questions') or fallback


def linked_evidence(response, question_response):
    rows = []
    for link in frappe.get_all('DD Answer Evidence Link', filters={'parent': question_response, 'parenttype':'FP Question Response'}, fields=['evidence', 'requirement_id', 'support_note']):
        evidence = frappe.get_doc('Field Evidence', link.evidence)
        origin = frappe.get_doc('FP Question Response', evidence.question_response)
        from fieldpulse.scout_lineage import evidence_origin_allowed
        if not evidence_origin_allowed(response, origin.task_response, frappe.get_doc) or evidence.upload_status != 'Uploaded': frappe.throw('Evidence is outside this response or not verified')
        rows.append(frappe._dict(name=evidence.name, evidence_type=evidence.evidence_type, caption=evidence.caption,
            gps_lat=evidence.gps_lat, gps_lng=evidence.gps_lng, accuracy_m=evidence.accuracy_m,
            description=evidence.get('description'), clarification_required=evidence.get('clarification_required'),
            metadata_origin=evidence.get('metadata_origin'), location_sampled_at=evidence.get('location_sampled_at'),
            captured_at=evidence.captured_at, requirement_id=link.requirement_id, support_note=link.support_note,
            question_response=question_response))
    return rows


@frappe.whitelist(methods=['POST'])
def sync_evidence_links(response, links):
    """Replace links atomically after upload. Retry-safe; never trusts answer media IDs."""
    from fieldpulse.api import _get_scout_profile_for_user
    scout = _get_scout_profile_for_user()
    frappe.db.sql('SELECT name FROM `tabFP Task Response` WHERE name=%s FOR UPDATE', [response])
    doc = frappe.get_doc('FP Task Response', response)
    task = frappe.get_doc('Field Task', doc.task)
    if doc.agent != scout.name or task.scout_profile != scout.name: frappe.throw('Not your response', frappe.PermissionError)
    frozen = doc.status != 'Draft' or task.status in {'Submitted', 'Approved', 'Cancelled', 'Awaiting authorization'}
    definitions = task_questions(task, [])
    if not definitions: frappe.throw('This task does not use the version 2 protocol')
    submitted = decode(links, [])
    if not isinstance(submitted, list) or len(submitted) > 5000: frappe.throw('Invalid evidence link batch')
    responses = frappe.get_all('FP Question Response', filters={'task_response':response}, fields=['name', 'question', 'question_code', 'answer_json'])
    by_code = {row.question_code: row for row in responses}
    answers = {row.question_code: decode(row.answer_json, {}) for row in responses}
    required = {}
    for question in definitions:
        config = decode(question['validation_json'])
        code = question['question_code']
        if visible(code, config, answers) and not (answers.get(code) or {}).get('blocked'):
            for rule in required_evidence(code, config, answers.get(code) or {}): required[rule['requirement_id']] = (code, rule)
    grouped = {row.name: [] for row in responses}
    seen = set()
    for link in submitted:
        key = link.get('requirement_id')
        if key not in required: frappe.throw('Evidence link has no active assigned requirement')
        code, rule = required[key]
        if code not in by_code: frappe.throw('Save the linked answer before attaching evidence')
        evidence_name = frappe.db.exists('Field Evidence', {'client_uuid':link.get('attachment_id')})
        if not evidence_name: frappe.throw('Upload linked evidence before finalisation')
        evidence = frappe.get_doc('Field Evidence', evidence_name)
        if evidence.scout != scout.name or evidence.field_task != task.name or evidence.upload_status != 'Uploaded': frappe.throw('Evidence belongs to another task or is unverified', frappe.PermissionError)
        origin = frappe.get_doc('FP Question Response', evidence.question_response)
        from fieldpulse.scout_lineage import evidence_origin_allowed
        if not evidence_origin_allowed(doc.name, origin.task_response, frappe.get_doc) or evidence.evidence_type != rule['kind']: frappe.throw('Evidence response or type does not match the requirement')
        if not str(link.get('support_note') or '').strip(): frappe.throw('State what required subject the linked file shows')
        identity = (key, evidence.name)
        if identity in seen: frappe.throw('Duplicate evidence link')
        seen.add(identity)
        grouped[by_code[code].name].append(dict(evidence=evidence.name, requirement_id=key, support_note=link['support_note']))
    if frozen:
        current = {(row.name, link['evidence'], link['requirement_id'], link['support_note']) for row in responses for link in frappe.get_all('DD Answer Evidence Link', filters={'parent':row.name, 'parenttype':'FP Question Response'}, fields=['evidence', 'requirement_id', 'support_note'])}
        incoming = {(parent, link['evidence'], link['requirement_id'], link['support_note']) for parent, values in grouped.items() for link in values}
        if doc.status == 'Submitted' and current == incoming: return {'linked':len(seen)}
        frappe.throw('Evidence links are frozen after submission')
    # Validate the entire batch before changing any answer.
    for row in responses:
        answer_doc = frappe.get_doc('FP Question Response', row.name)
        answer_doc.set('evidence_links', grouped[row.name])
        answer_doc.save(ignore_permissions=True)
    return {'linked':len(seen)}


@frappe.whitelist()
def question_editor_settings(project, question=None, configuration=None):
    from fieldpulse.scout_submissions import require_reviewer
    require_reviewer()
    from fieldpulse.project_questionnaires import editor_settings
    return editor_settings(project,question,configuration)


@frappe.whitelist(methods=['POST'])
def confirm_project_questionnaire(project, expected_modified):
    from fieldpulse.project_questionnaires import confirm
    return confirm(project,expected_modified)
