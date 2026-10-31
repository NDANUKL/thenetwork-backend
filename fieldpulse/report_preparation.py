"""Assemble factual report drafts without asking coordinators to rewrite fieldwork."""
import json
import frappe
from fieldpulse.customer_coverage import build_check, decode, answer_present


def prepare_content(reference):
    from fieldpulse.scout_submissions import submission_detail
    projects = frappe.get_all('Field Request', filters={'diaspora_request': reference, 'status': ['!=', 'Cancelled']}, pluck='name')
    tasks = frappe.get_all('Field Task', filters={'field_request': ['in', projects], 'status': ['not in', ['Cancelled', 'Rejected']]}, fields=['name', 'status', 'field_request', 'task_brief_version']) if projects else []
    if not tasks or any(task.status != 'Approved' for task in tasks): frappe.throw('All active scout tasks must be approved')
    if any(getattr(task, 'task_brief_version', None) for task in tasks):
        from fieldpulse.task_brief_workflow import coverage_ready
        if not coverage_ready(projects): frappe.throw('Approve allocations covering every required Task Brief check')
    rows, sources, visits, scopes, media = [], [], [], [], {}
    complete = True
    for item in tasks:
        task = frappe.get_doc('Field Task', item.name)
        project = frappe.get_doc('Field Request', task.field_request)
        response = frappe.db.get_value('FP Task Response', {'task': task.name, 'status': 'Submitted', 'qa_status': 'Passed', 'reviewed_by': ['is', 'set']}, 'name', order_by='creation desc')
        if not response: frappe.throw('A task is missing its reviewed, approved submission')
        detail = submission_detail(response)
        sources.append(dict(task=task.name, response=response))
        if detail.get('brief'):
            pinned, submission = detail['brief'], detail['submission']
            scopes.append(dict(project=project.name, title=pinned['brief']['title'], reference=pinned['brief_id'],
                version=pinned['version'], scope=pinned['brief']['scope'], retrospective=False))
            site, arrival = pinned['site'], submission.get('arrival') or {}
            visits.append(dict(task=task.name, site=site.get('label'), address=site.get('address'),
                date=arrival.get('captured_at'), arrival='Inside', methods='Scout observations and coordinator-reviewed evidence.'))
            for check in pinned['brief']['checks']:
                if check['id'] not in pinned['check_ids']: continue
                answer = submission['answers'].get(check['id']) or {}
                observed = answer.get('status') == 'observed'
                # An inability retracts any earlier observation. Keep the original
                # value in the source response for audit, never as a report finding.
                value = answer.get('value') if observed else None
                findings = ', '.join(value) if isinstance(value, list) else str(value or '')
                if not findings:
                    findings = 'See the recorded field evidence.' if observed else answer.get('explanation') or 'No observation recorded.'
                gaps = [] if observed else [answer.get('explanation') or 'This check was not verified.']
                evidence_ids = [item.name for item in detail['evidence'] if item.field_check_id == check['id']]
                rows.append(dict(check_id=task.name+':'+check['id'], project=project.name, task=task.name,
                    customer_question=check['instruction'], findings=findings,
                    assessment='Supported finding' if observed else 'Not verified', basis='Directly observed' if observed else 'Not recorded',
                    basis_detail='', limitations='\n'.join(gaps), limitation_acknowledged=0,
                    answer_refs_json=json.dumps([response+':'+check['id']]), evidence_ids_json=json.dumps(evidence_ids),
                    recorded_gaps_json=json.dumps(gaps)))
            if submission.get('additional_observations'):
                visits[-1]['methods'] += '\nAdditional observations: '+submission['additional_observations']
            for evidence in detail['evidence']:
                media[evidence.name] = dict(evidence=evidence.name, evidence_type=evidence.evidence_type,
                    caption=evidence.caption or next((check['instruction'] for check in pinned['brief']['checks'] if check['id']==evidence.field_check_id), ''), include_client=0)
            continue
        assigned = detail.get('client_request') or decode(task.get('client_request_snapshot'), {}) or {}
        review = assigned.get('questionnaire_review') or {}
        answers = {a.question_code: decode(a.answer_json, {}) for a in detail.get('answers') or []}
        checklist = []
        for question in detail.get('questions') or []:
            config = decode(question.get('validation_json'), {}) or {}
            if config.get('group') == 'shared' or question.question_code in {'S1','S2','S3','S4'}: continue
            if (config.get('group') == 'final' or question.question_code == 'S_EXTRA') and not answer_present(answers.get(question.question_code)): continue
            checklist.append(dict(check_id=question.question_code, customer_question=question.label, question_codes=[question.question_code]))
        mapping = dict(complete=bool(checklist), checks=checklist,
            reference=review.get('scope_reference') or task.get('questionnaire'),
            version=review.get('scope_version') or task.get('questionnaire_version'),
            scope=review.get('scope') or assigned.get('task_scope') or assigned.get('client_request') or task.get('task_brief'),
            reviewed_by=review.get('reviewed_by'), retrospective=False)
        complete &= bool(mapping.get('complete'))
        scopes.append(dict(project=project.name, title=project.get('project_title') or project.name,
            reference=mapping.get('reference'), version=mapping.get('version'), scope=mapping.get('scope'),
            retrospective=mapping.get('retrospective'), reviewed_by=mapping.get('reviewed_by')))
        assigned = detail.get('client_request') or {}
        site = assigned.get('site_reference') or {}
        arrival = detail.get('arrival') or {}
        visits.append(dict(task=task.name, site=site.get('location_name') or assigned.get('site_or_item') or project.get('project_title') or 'Site not recorded',
            address=site.get('address') or 'Address not recorded', date=arrival.get('captured_at') or 'Visit date not recorded',
            arrival=arrival.get('status') or 'Arrival not recorded',
            methods='Recorded questionnaire answers. ' + ('Verified media types: ' + ', '.join(sorted({e.evidence_type for e in detail.get('evidence') or []})) + '. ' if detail.get('evidence') else 'No verified media records. ') + 'Source basis is stated separately for each finding.'))
        checks = mapping.get('checks') or [dict(check_id='unmapped', customer_question='Assigned questionnaire unavailable', question_codes=[])]
        for check in checks:
            row = build_check(check, detail, project, task)
            row['check_id'] = task.name + ':' + check['check_id']
            if arrival.get('status') != 'Inside' or not arrival.get('captured_at'):
                gap = 'The approved source does not contain a verified arrival and visit date.'
                recorded = decode(row['recorded_gaps_json'], []) + [gap]
                row.update(assessment='Not verified', limitations=(row['limitations'] + '\n' + gap).strip(), recorded_gaps_json=json.dumps(recorded))
            if not mapping.get('complete'):
                row.update(assessment='Not verified', limitations='The assigned questionnaire could not be recovered from this approved submission.')
            rows.append(row)
        for evidence in detail.get('evidence') or []:
            if evidence.evidence_type in {'Photo', 'Video'}:
                media[evidence.name] = dict(evidence=evidence.name, evidence_type=evidence.evidence_type,
                    caption=evidence.caption or '', include_client=0)
    supported = sum(row['assessment'] == 'Supported finding' for row in rows)
    pending = len(rows) - supported
    summary = f'{len(tasks)} approved scout submission(s) cover {len(scopes)} recorded site assignment(s). Of {len(rows)} field checks, {supported} have recorded supporting findings and {pending} require a limitation or source-basis review.'
    # Add actual findings, rather than a generic introduction or inferred conclusions.
    summary += '\n\n' + '\n\n'.join(row['customer_question'] + '\n' + (row['findings'][:700] if row['assessment'] == 'Supported finding' else 'Not verified / requires review: ' + (row['limitations'] or 'Source basis not recorded')) for row in rows[:4])
    return dict(executive_summary=summary, findings='\n\n'.join(row['customer_question'] + '\n' + row['findings'] for row in rows),
        limitations='\n\n'.join(row['customer_question'] + ': ' + row['limitations'] for row in rows if row['limitations']),
        report_checks=rows, report_evidence=list(media.values()), review_sources_json=json.dumps(sources),
        coverage_snapshot_json=json.dumps(dict(kind="assigned_questionnaire", complete=complete, checks=rows)), scope_snapshot_json=json.dumps(scopes),
        visit_snapshot_json=json.dumps(visits), scope_coverage_reviewed=0, evidence_selection_reviewed=0,
        report_file=None, generated_from_hash=None, review_signatory=None, review_signed_at=None)


def validate_snapshot(doc):
    if doc.is_new() and doc.get('coverage_snapshot_json') and not frappe.flags.dd_preparing_report:
        frappe.throw('Create sourced report drafts through report preparation')
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and not frappe.flags.dd_preparing_report:
        for key in ('coverage_snapshot_json', 'scope_snapshot_json', 'visit_snapshot_json', 'review_sources_json', 'review_signatory', 'review_signed_at'):
            if doc.get(key) != previous.get(key): frappe.throw('Report source snapshots and sign-off are managed by report preparation')
    from fieldpulse.customer_coverage import validate_report
    validate_report(doc, approving=doc.status == 'Approved')


def pdf_context(doc, selected):
    selected_ids = {evidence.name: index for index, (_, evidence) in enumerate(selected, 1)}
    checks = []
    for row in doc.get('report_checks') or []:
        checks.append(dict(question=row.customer_question, findings=row.findings, assessment=row.assessment,
            basis=row.basis, basis_detail=row.get('basis_detail'), limitations=row.get('limitations'),
            evidence_refs=[f'E{selected_ids[name]:03d}' for name in decode(row.get('evidence_ids_json'), []) if name in selected_ids]))
    return dict(checks=checks, scopes=decode(doc.get('scope_snapshot_json'), []), visits=decode(doc.get('visit_snapshot_json'), []))
