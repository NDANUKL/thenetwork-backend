"""Customer questions reuse the already selected scout checks and immutable pins."""
import hashlib
import json
from uuid import uuid4


def decode(value, fallback=None):
    try: return json.loads(value) if isinstance(value, str) else value if value is not None else fallback
    except (ValueError, TypeError): return fallback


def codes(value):
    if isinstance(value, list): return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or '').replace('\n', ',').split(',') if item.strip()]


def signature(rows, reference):
    values = [dict(check_id=row.get('check_id'), customer_question=row.get('customer_question'), question_codes=codes(row.get('question_codes'))) for row in rows]
    return hashlib.sha256(json.dumps([reference, values], sort_keys=True).encode()).hexdigest()


def validate_project(doc):
    rows = doc.get('customer_checks') or []
    if not rows and not doc.get('customer_checks_confirmed'): return
    import frappe
    questions = frappe.get_all('FP Question', filters={'questionnaire': doc.get('scout_questionnaire'), 'active': 1}, fields=['name', 'question_code', 'label', 'validation_json'])
    selected = {row.question for row in doc.get('scout_checks') or []}
    available = {q.question_code: q.label for q in questions if q.name in selected or (decode(q.validation_json, {}) or {}).get('group') in {'shared', 'final'}}
    seen = set()
    for row in rows:
        if not row.get('check_id'): row.check_id = str(uuid4())
        if row.check_id in seen: frappe.throw('Customer check identifiers must be unique')
        seen.add(row.check_id)
        if not str(row.get('customer_question') or '').strip(): frappe.throw('Write each agreed customer question')
        linked = codes(row.get('question_codes'))
        if not linked or len(set(linked)) != len(linked) or not set(linked) <= set(available):
            frappe.throw('Link every customer question to unique checks selected for this project')
        row.question_codes = ', '.join(linked)
        row.linked_checks = '\n'.join(available[code] for code in linked)
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    current = signature(rows, doc.get('customer_scope_reference'))
    if previous and previous.get('customer_checks_confirmed'):
        if current != signature(previous.get('customer_checks') or [], previous.get('customer_scope_reference')) or previous.get('field_brief') != doc.get('field_brief') or not doc.get('scout_checks_confirmed'):
            doc.customer_checks_confirmed = 0
    if doc.get('customer_checks_confirmed'):
        if not rows or not doc.get('scout_checks_confirmed'): frappe.throw('Confirm selected scout checks and customer questions together')
        from fieldpulse.scout_submissions import require_reviewer
        require_reviewer()
        quote = frappe.get_doc('DD Quotation', doc.get('customer_scope_reference'))
        if quote.request != doc.get('diaspora_request') or quote.status != 'Accepted': frappe.throw('Use this request\'s accepted quotation as the scope reference')
        version = str(quote.get('version') or 1)
        if previous and previous.get('customer_checks_confirmed') and str(previous.get('customer_scope_version') or '') != version:
            doc.customer_checks_confirmed = 0
            return
        doc.customer_scope_version = version
        if not previous or not previous.get('customer_checks_confirmed'):
            doc.customer_checks_reviewed_by = frappe.session.user
            doc.customer_checks_reviewed_at = frappe.utils.now_datetime()


def project_snapshot(project):
    return dict(complete=bool(project.get('customer_checks_confirmed') and project.get('customer_checks') and project.get('customer_scope_reference') and project.get('customer_scope_version') and project.get('customer_checks_reviewed_by')),
        reference=project.get('customer_scope_reference'), version=project.get('customer_scope_version'),
        scope=project.get('field_brief'), reviewed_by=project.get('customer_checks_reviewed_by'),
        reviewed_at=str(project.get('customer_checks_reviewed_at') or ''),
        checks=[dict(check_id=row.check_id, customer_question=row.customer_question, question_codes=codes(row.question_codes)) for row in project.get('customer_checks') or []])


def task_mapping(task, project):
    pinned = (decode(task.get('client_request_snapshot'), {}) or {}).get('customer_coverage')
    result = pinned or project_snapshot(project)
    return dict(result, retrospective=not bool(pinned))


def source_basis(answers):
    """Unknown provenance stays unknown; silence never becomes observation."""
    observed, reported, independent = False, False, False
    def inspect(value):
        nonlocal observed, reported, independent
        if not isinstance(value, dict): return
        basis = str(value.get('source_type') or '').lower()
        result = str(value.get('result') or '').lower()
        independent |= basis == 'independently checked'
        observed |= basis == 'combination'
        reported |= basis in {'representative','document or record','combination'}
        reported |= bool(value.get('source_role') or value.get('source') or 'reported' in basis or 'reported' in result)
        observed |= 'observed' in result or basis in {'direct observation', 'directly observed'}
        for item in (value.get('items') or {}).values(): inspect(item)
    for answer in answers: inspect(answer)
    count = sum([observed, reported, independent])
    return 'Mixed sources' if count > 1 else 'Directly observed' if observed else 'Reported by others' if reported else 'Independently checked' if independent else 'Not recorded'


def answer_present(answer):
    if not isinstance(answer, dict): return answer not in (None, '', [], {})
    return bool(answer.get('result') or answer.get('results') or str(answer.get('text') or '').strip() or any(answer_present(item) for item in (answer.get('items') or {}).values()))


def required_review_errors(detail):
    errors = [error for summary in detail.get('summary') or [] for error in summary.get('errors') or []]
    answers = {answer.question_code: answer for answer in detail.get('answers') or []}
    for question in detail.get('questions') or []:
        config = decode(question.get('validation_json'), {}) or {}
        if not config.get('mandatory_evidence'): continue
        answer = answers.get(question.question_code)
        kinds = {item.evidence_type for item in detail.get('evidence') or [] if answer and item.question_response == answer.name}
        for kind in ('Photo', 'Video'):
            if kind not in kinds: errors.append('Required ' + kind.lower() + ' missing for: ' + question.label)
    return list(dict.fromkeys(errors))


def build_check(check, detail, project, task):
    from fieldpulse.report_findings import finding_text
    by_code = {a.question_code: a for a in detail.get('answers') or []}
    questions = {q.question_code: q for q in detail.get('questions') or []}
    summaries = {row['code']: row for row in detail.get('summary') or []}
    all_answers = {code: decode(row.answer_json, {}) for code, row in by_code.items()}
    gaps, narrative, media, values, refs = [], [], [], [], []
    for code in check['question_codes']:
        row, question = by_code.get(code), questions.get(code)
        value = all_answers.get(code)
        label = question.label if question else code
        summary = summaries.get(code) or {}
        if not row or not question or not answer_present(value):
            gaps.append('No approved answer for: ' + label)
            continue
        refs.append(row.name)
        values.append(value)
        text, limitations = finding_text(question, row.answer_json, all_answers, row.get('answer_text') or '')
        narrative.append(label + '\n' + text)
        if isinstance(value, dict) and (value.get('blocked') or any(token in str(value.get('result') or '').lower() for token in ('unable', 'not confirmed', 'not found', 'inaccessible'))): gaps.append('Not verified: ' + label)
        gaps.extend(summary.get('errors') or [])
        if (decode(question.get('validation_json'), {}) or {}).get('mandatory_evidence'):
            kinds = {e.evidence_type for e in detail.get('evidence') or [] if e.question_response == row.name}
            gaps.extend('Required ' + kind.lower() + ' not recorded for: ' + label for kind in ('Photo', 'Video') if kind not in kinds)
        if summary.get('skipped'): gaps.append('Check not performed for this visit outcome: ' + label)
        gaps.extend(limitations)
        media.extend(e.name for e in detail.get('evidence') or [] if e.question_response == row.name)
    basis = source_basis(values)
    return dict(check_id=project.name + ':' + check['check_id'], project=project.name,
        customer_question=check['customer_question'], findings='\n\n'.join(narrative) or 'Not verified - no approved answer addresses this customer question.',
        assessment='Not verified' if gaps or basis == 'Not recorded' else 'Supported finding', basis=basis,
        basis_detail='', limitations='\n'.join(dict.fromkeys(gaps)), limitation_acknowledged=0,
        answer_refs_json=json.dumps(refs), evidence_ids_json=json.dumps(sorted(set(media))),
        recorded_gaps_json=json.dumps(list(dict.fromkeys(gaps))), task=task.name)


def validate_report(doc, approving=False):
    import frappe
    snapshot = decode(doc.get('coverage_snapshot_json'), {}) or {}
    expected = snapshot.get('checks') or []
    rows = doc.get('report_checks') or []
    if not snapshot.get('complete') or not expected or not rows:
        if approving: frappe.throw('Refresh this draft from the approved assigned questionnaire before approval')
        return
    by_id = {row.check_id: row for row in rows}
    if len(by_id) != len(rows) or set(by_id) != {item['check_id'] for item in expected}: frappe.throw('Every assigned questionnaire question must remain in the report')
    for item in expected:
        row = by_id[item['check_id']]
        for key in ('project', 'task', 'customer_question', 'answer_refs_json', 'evidence_ids_json', 'recorded_gaps_json'):
            if row.get(key) != item.get(key): frappe.throw('Report coverage sources are frozen; refresh the draft from approved submissions')
        if row.assessment not in {'Supported finding', 'Not verified'}: frappe.throw('Choose a finding or an explicit Not verified limitation')
        if not str(row.get('findings') or '').strip(): frappe.throw('Retain a finding or explanation for every customer question')
        if row.assessment == 'Supported finding':
            if decode(item.get('recorded_gaps_json'), []) or not decode(item.get('answer_refs_json'), []): frappe.throw('Unresolved recorded gaps cannot be represented as verified findings')
            if row.basis not in {'Directly observed', 'Reported by others', 'Independently checked', 'Mixed sources'}: frappe.throw('Record the source basis of each supported finding')
            if row.basis != item.get('basis') and not str(row.get('basis_detail') or '').strip(): frappe.throw('Explain changes to a finding\'s source basis')
        elif approving and (row.get('limitation_acknowledged') not in (1, True, '1') or not str(row.get('limitations') or '').strip()):
            frappe.throw('Explain and acknowledge every Not verified finding before approval')
    if approving and doc.get('scope_coverage_reviewed') not in (1, True, '1'): frappe.throw('Confirm review of the findings, evidence and limitations before report approval')
