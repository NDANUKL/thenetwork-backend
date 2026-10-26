"""Version 2 questionnaire contract. Pure rules used at dispatch and submission."""
import copy
import json
import re
import math

EXCEPTION_REASONS = [
    'Photography or recording prohibited', 'Permission refused',
    'Subject or item inaccessible', 'Site or item not found', 'Safety concern',
    'Technical problem', 'Other',
]
KINDS = {'Photo', 'Video', 'Document'}
BLOCKED = re.compile(r'unable|not demonstrated|not confirmed|missing or unreadable|no matching|not found|inaccessible|declined|could not be reached|unwilling|not eligible|no representative', re.I)
SHARED_V2 = [
    dict(code='S1', label='Does the site match the assigned location?', answer_type='single', result_options=['Yes', 'No', 'Unable to confirm'], text_when=['No', 'Unable to confirm'], evidence=[dict(id='photo', kind='Photo', subject='One photo showing the location reached.', when=['No', 'Unable to confirm'])]),
    dict(code='S2', label='What access did you obtain?', answer_type='single', result_options=['Full access', 'Partial access', 'No access'], text_when=['Partial access', 'No access'], evidence=[]),
]
CLOSING_V2 = dict(code='S_EXTRA', label='Is there anything else relevant to this task?', answer_type='text', optional=True, evidence=[])


def decode(raw, default=None):
    if raw is None or raw == '': return copy.deepcopy(default)
    return json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw)


def validate_config(config, assigned=False):
    if not isinstance(config, dict) or config.get('protocol_version') != 2:
        raise ValueError('A version 2 question configuration is required')
    if config.get('answer_type') not in {'single', 'multi', 'text', 'checklist', 'interview', 'custom'}:
        raise ValueError('Choose a supported answer type')
    if not isinstance(config.get('evidence'), list): raise ValueError('Specify the evidence policy, including an empty list for no media')
    if config['answer_type'] in {'single', 'multi', 'checklist', 'interview', 'custom'} and not config.get('result_options'):
        raise ValueError('Specify answer choices')
    options = config.get('result_options', [])
    if len(options) != len(set(options)): raise ValueError('Answer choices must be unique')
    ids = []
    for rule in config['evidence']:
        if rule.get('kind') not in KINDS or not str(rule.get('subject', '')).strip() or not re.fullmatch(r'[a-zA-Z0-9_-]+', rule.get('id', '')):
            raise ValueError('Choose Photo, Video or Document and describe exactly what each attachment must show')
        if rule.get('when') and not set(rule['when']) <= set(options): raise ValueError('Evidence conditions must use allowed answers')
        ids.append(rule['id'])
    if len(ids) != len(set(ids)): raise ValueError('Media requirement IDs must be unique')
    if assigned and config['answer_type'] in {'checklist', 'interview', 'custom'}:
        items = config.get('items', [])
        if not items: raise ValueError('Add at least one item or approved question to this checklist')
        item_ids = [item.get('id') for item in items]
        if any(not re.fullmatch(r'[a-zA-Z0-9_-]+', value or '') for value in item_ids) or len(item_ids) != len(set(item_ids)):
            raise ValueError('Assigned items need unique stable IDs')
        if any(not str(item.get('label', '')).strip() for item in items): raise ValueError('Each assigned item needs a description')
        if any(item.get('video_demonstration_required') and not item.get('demonstration_required') for item in items): raise ValueError('Assign the demonstration before requiring its video')
        if config['answer_type'] == 'custom':
            for item in items:
                if 'evidence' not in item: raise ValueError('Choose an explicit evidence policy for each custom question')
                validate_config(dict(config, answer_type='single', items=[], evidence=item['evidence']), assigned=False)


def resolve_config(template, assignment):
    """Resolve coordinator settings without permitting arbitrary protocol overrides."""
    config = copy.deepcopy(template)
    assignment = decode(assignment, {})
    allowed = {'items', 'enabled', 'confirmation_method', 'confirmation_subject', 'physical_inspection',
               'walkthrough_subject', 'delivery_document_subject', 'verification_subject', 'additional_evidence'}
    if set(assignment) - allowed: raise ValueError('Unknown coordinator configuration fields')
    for key in allowed - {'additional_evidence'}:
        if key in assignment: config[key] = assignment[key]
    if config.get('assigned_only') and not assignment.get('enabled'): return None
    if config.get('previous_required') and not assignment.get('enabled'): return None
    if config.get('answer_type') in {'checklist', 'interview', 'custom'} and not config.get('items'):
        config['items'] = [dict(id=f'item-{i}', label=label) for i, label in enumerate(config.get('default_items', []), 1)]
    if config.get('quantity_required'):
        for item in config.get('items', []): item['quantity_required'] = True
    if config.get('walkthrough_subject'):
        config['evidence'].append(dict(id='walkthrough', kind='Video', subject=config['walkthrough_subject'], once=True))
    if config.get('confirmation'):
        method = config.get('confirmation_method')
        if method not in {'Verbal', 'Written', 'Authorised photo'}: raise ValueError('Choose a confirmation method: Verbal, Written or Authorised photo')
        if method != 'Verbal':
            if not str(config.get('confirmation_subject', '')).strip(): raise ValueError('Describe the document or information the scout is permitted to collect')
            config['evidence'].append(dict(id='confirmation', kind='Document' if method == 'Written' else 'Photo', subject=config['confirmation_subject'], once=True))
    if config.get('inspection') and config.get('physical_inspection'):
        config['evidence'].append(dict(id='physical', kind='Photo', subject='Show only the specified physical document fields.', when=['Matches', 'Differs', 'Missing or unreadable']))
    for key, rule_id in [('delivery_document_subject', 'delivery-document'), ('verification_subject', 'verification')]:
        if config.get(key): config['evidence'].append(dict(id=rule_id, kind='Photo', subject=config[key], once=True))
    config['evidence'].extend(assignment.get('additional_evidence', []))
    validate_config(config, assigned=True)
    return config


def visible(code, config, answers):
    if config.get('group') == 'final' or config.get('group') == 'shared': return True
    opening = answers.get('S1') or {}
    if opening.get('site_not_found'): return False
    if config.get('authorisation_required') and (answers.get('S2') or {}).get('authorisation_disputed'): return False
    if code.startswith('15.') and code != '15.1' and (answers.get('15.1') or {}).get('result') != 'Eligible and agreed': return False
    if config.get('record_gate'):
        first = answers.get(code.split('.')[0] + '.1') or {}
        if first.get('result') not in {'Matching record found', 'Record found with differences'}: return False
    return True


def targets(code, config, answer):
    if config['answer_type'] in {'checklist', 'interview', 'custom'}:
        return [(item['id'], item, (answer.get('items') or {}).get(item['id']) or {}) for item in config.get('items', [])]
    return [('', {}, answer)]


def required_evidence(code, config, answer):
    result = []
    seen_once = set()
    for item_id, item, value in targets(code, config, answer):
        selected = value.get('results', []) if config['answer_type'] == 'multi' else [value.get('result')]
        for rule in item.get('evidence', config['evidence']):
            if rule.get('when') and not set(selected).intersection(rule['when']): continue
            if rule.get('once') and rule['id'] in seen_once: continue
            # Confirmation is not a demand to photograph a nonexistent/refused record.
            if rule['id'] == 'confirmation' and selected and any(BLOCKED.search(str(s or '')) for s in selected): continue
            key = f"{code}:{'' if rule.get('once') else item_id}:{rule['id']}"
            result.append(dict(rule, requirement_id=key, item_id=item_id, item_label=item.get('label', '')))
            if rule.get('once'): seen_once.add(rule['id'])
        if config.get('demonstration') and item.get('video_demonstration_required') and value.get('demonstration') in {'Demonstrated without an obvious issue', 'Demonstrated with an issue'}:
            result.append(dict(id='demonstration', kind='Video', subject='Demonstrate ' + item['label'], requirement_id=f'{code}:{item_id}:demonstration', item_id=item_id))
    return result


def explanation(value, answers):
    if str(value.get('explanation') or value.get('text') or '').strip(): return True
    ref = value.get('explanation_ref')
    if ref not in {'S1', 'S2'}: return False
    shared = answers.get(ref) or {}
    return bool(str(shared.get('text') or '').strip()) and shared.get('result') in {'No', 'Unable to confirm', 'Partial access', 'No access'}


def evaluate_question(code, config, answer, answers, media):
    """Returns unexplained errors, review limitations and per-requirement coverage."""
    errors, reasons, coverage = [], [], []
    if not visible(code, config, answers): return dict(errors=[], reasons=[], evidence=[], skipped=True)
    if config.get('group') == 'final': return dict(errors=[], reasons=[], evidence=[], skipped=False)
    if not isinstance(answer, dict): answer = {}
    if answer.get('blocked'):
        if config.get('group') != 'service': errors.append('Opening questions must be answered')
        if not explanation(answer, answers): errors.append('Explain why this check could not be completed')
        reasons.append('Unable to check')
        return dict(errors=errors, reasons=reasons, evidence=[], skipped=False)
    if config.get('source_basis_required'):
        if answer.get('source_type') not in {'Direct observation','Representative','Document or record','Combination'}:
            errors.append(code + ': record whether the finding was observed or obtained from another source')
        elif answer.get('source_type') != 'Direct observation' and not str(answer.get('source_role') or '').strip():
            errors.append(code + ': record the source role or record reference')
    for item_id, item, value in targets(code, config, answer):
        label = item.get('label') or code
        result = value.get('result')
        selected = value.get('results', []) if config['answer_type'] == 'multi' else [result]
        options = config['result_options']
        if config['answer_type'] == 'custom' and not item.get('not_applicable_permitted'): options = [o for o in options if o != 'Not applicable']
        if config['answer_type'] == 'text':
            if not str(value.get('text') or '').strip() and not config.get('optional'): errors.append(label + ': finding missing')
        elif not selected or any(s not in options for s in selected): errors.append(label + ': choose an allowed answer')
        if config['answer_type'] == 'multi' and len(selected) > 1 and any(BLOCKED.search(str(s or '')) for s in selected): errors.append(label + ': select the unable outcome on its own')
        blocked = any(BLOCKED.search(str(s or '')) for s in selected)
        needs_text = config.get('text_required') or bool(set(selected).intersection(config.get('text_when', [])))
        refusal = any(s in {'Declined to answer', 'Eligible but declined', 'Not eligible'} or str(s or '').startswith('No representative') for s in selected)
        if ((blocked and not refusal) or needs_text) and not explanation(value, answers): errors.append(label + ': finding or explanation missing')
        if blocked: reasons.append(label + ': ' + ', '.join(str(s) for s in selected))
        if value.get('source_type') in {'Representative', 'Document or record', 'Combination'} or any('reported' in str(s or '').lower() for s in selected) or (config.get('source_required') and not any(re.search(r'unable|unwilling|no representative|could not be reached', str(s or ''), re.I) for s in selected)):
            if not str(answer.get('source_role') or value.get('source_role') or '').strip(): errors.append(label + ': source office or role missing')
        if config.get('confirmed_detail') and result in {'Confirmed', 'Recorded'} and not str(value.get('text') or '').strip(): errors.append(label + ': confirmed detail missing')
        if value.get('identity_differs') and not str(value.get('text') or '').strip(): errors.append(label + ': describe the business identity difference')
        if config.get('condition') and result == 'Observed available' and value.get('condition') not in {'No obvious visible issues', 'Visible damage or deterioration', 'Unable to assess'}:
            errors.append(label + ': inspected item condition missing')
        if value.get('condition') == 'Visible damage or deterioration' and not str(value.get('text') or '').strip(): errors.append(label + ': describe the damage')
        if config.get('identifier') and result == 'Present' and value.get('identifier') not in {'Identifier matches', 'Identifier differs', 'Identifier unavailable or unreadable', 'No identifier supplied'}:
            errors.append(label + ': identifier result missing')
        if value.get('identifier') == 'Identifier differs' and not str(value.get('text') or '').strip(): errors.append(label + ': describe the identifier difference')
        if item.get('quantity_required') and not blocked and value.get('quantity') in (None, ''): errors.append(label + ': quantity missing')
        if item.get('reading_required') and not blocked and not str(value.get('text') or '').strip(): errors.append(label + ': assigned reading missing')
        if value.get('quantity') not in (None, ''):
            try:
                amount = float(value['quantity'])
                if not math.isfinite(amount) or amount < 0: raise ValueError()
            except (TypeError, ValueError): errors.append(label + ': enter a nonnegative quantity')
        if item.get('demonstration_required'):
            if value.get('demonstration') not in {'Demonstrated without an obvious issue', 'Demonstrated with an issue', 'Not demonstrated'}: errors.append(label + ': demonstration result missing')
            elif value['demonstration'] != 'Demonstrated without an obvious issue' and not explanation(value, answers): errors.append(label + ': explain the demonstration result')
            if value.get('demonstration') == 'Not demonstrated': reasons.append(label + ': Not demonstrated')
    if answer.get('site_not_found'):
        if code != 'S1' or answer.get('result') == 'Yes': errors.append('A site-not-found attempt needs a location issue')
        reasons.append('Site not found; service checks not attempted')
    if code == 'S1' and answer.get('result') in {'No', 'Unable to confirm'}: reasons.append('Location requires review')
    if code == 'S2' and answer.get('result') in {'Partial access', 'No access'}: reasons.append('Access limitation')
    if code == 'S2' and answer.get('authorisation_disputed'):
        if not str(answer.get('text') or '').strip(): errors.append('Explain the disputed authorisation')
        reasons.append('Authorisation disputed; authorised checks paused')
    rules = required_evidence(code, config, answer)
    allowed = {r['requirement_id'] for r in rules}
    links = answer.get('evidence_links') or []
    exceptions = answer.get('exceptions') or {}
    if set(exceptions) - allowed: errors.append('Evidence exception does not match an active requirement')
    for rule in rules:
        key = rule['requirement_id']
        matched = [m for m in media if m.get('requirement_id') == key and m.get('evidence_type') == rule['kind'] and str(m.get('caption') or '').strip()]
        exception = exceptions.get(key) or {}
        state = 'Attached' if matched else 'Missing'
        if not matched:
            if exception.get('reason') in EXCEPTION_REASONS and (exception['reason'] != 'Other' or str(exception.get('detail') or '').strip()):
                state = 'Unavailable'
                reasons.append(key + ': evidence unavailable - ' + exception['reason'] + ('; ' + exception['detail'] if exception.get('detail') else ''))
            else: errors.append(key + ': required ' + rule['kind'].lower() + ' missing or unexplained')
        coverage.append(dict(rule, state=state))
    if any(link.get('requirement_id') not in allowed for link in links): errors.append('Evidence link does not match an active requirement')
    return dict(errors=errors, reasons=reasons, evidence=coverage, skipped=False)


def evaluate(questions, answers, evidence, arrival, location=None, review=None):
    from fieldpulse.scout_protocol import arrival_result
    workflow = any(decode(q['validation_json'], {}).get('visit_workflow_version') == 2 for q in questions)
    if workflow:
        computed = arrival_result(arrival, location or {}, strict=True)
        arrival = dict(arrival, **computed)
        if (review or {}).get('visit_route') == 'arrival_exception':
            errors = []
            if not str((review or {}).get('arrival_exception_reason') or '').strip(): errors.append('Explain the unsuccessful arrival check')
            if answers or any(evidence.values()): errors.append('An arrival exception cannot include questionnaire answers or captured evidence')
            if arrival['status'] == 'Inside': errors.append('Verified arrivals must use the visit findings route')
            return dict(errors=errors, reasons=['Arrival exception: ' + str((review or {}).get('arrival_exception_reason') or ''), 'No verified arrival; fieldwork has not been completed'], summary=[], status='Needs review')
        if arrival['status'] != 'Inside':
            return dict(errors=['Verified arrival is required before opening or answering the questionnaire'], reasons=['Arrival not verified'], summary=[], status='Needs review')
    errors, reasons, summary = [], [], []
    for question in questions:
        code = question['question_code']
        config = decode(question['validation_json'], {})
        result = evaluate_question(code, config, answers.get(code) or {}, answers, evidence.get(code, []))
        errors.extend(code + ': ' + message for message in result['errors'])
        reasons.extend(code + ': ' + message for message in result['reasons'])
        summary.append(dict(code=code, label=question['label'], **result))
        if workflow:
            config = decode(question['validation_json'], {})
            answer = answers.get(code) or {}
            for rule in required_evidence(code, config, answer):
                item_value = (answer.get('items') or {}).get(rule.get('item_id'), {}) if rule.get('item_id') else answer
                selected = item_value.get('results', []) if config['answer_type'] == 'multi' else [item_value.get('result')]
                if not rule.get('requires_detail') and not set(selected).intersection(rule.get('detail_when', [])): continue
                matches = [row for row in evidence.get(code, []) if row.get('requirement_id') == rule['requirement_id']]
                if matches and not str(item_value.get('text') or '').strip() and not any(str(row.get('description') or '').strip() for row in matches):
                    errors.append(rule['requirement_id'] + ': describe the issue or unclear subject in the finding or file description')
    if arrival.get('status') != 'Inside':
        if not str(arrival.get('exception_reason') or '').strip(): errors.append('Explain the unverified arrival location')
        reasons.append('Arrival location unverified: ' + arrival.get('status', 'Invalid GPS'))
    seen = set()
    unverified_capture = False
    for rows in evidence.values():
        for row in rows:
            if row.get('name') in seen: continue
            seen.add(row.get('name'))
            if workflow and row.get('clarification_required') and not str(row.get('description') or '').strip(): errors.append('Describe the unclear subject in ' + str(row.get('name')))
            if row.get('evidence_type') not in {'Photo','Video'}: continue
            check = arrival_result(dict(latitude=row.get('gps_lat'), longitude=row.get('gps_lng'), accuracy_m=row.get('accuracy_m'), captured_at=row.get('captured_at')), location or {}, strict=workflow)
            if workflow and row.get('metadata_origin') != 'Camera':
                errors.append('Photo/video evidence must come from the on-site camera: ' + str(row.get('name')))
            if check['status'] != 'Inside':
                unverified_capture = True
                reasons.append('Evidence capture location unverified: ' + str(row.get('name')))
            if workflow:
                from fieldpulse.scout_visit import sample_is_contemporaneous
                if not sample_is_contemporaneous(row.get('captured_at'), row.get('location_sampled_at')):
                    unverified_capture = True
                    reasons.append('Capture GPS sample time needs review: ' + str(row.get('name')))
    capture_explanation = (review or {}).get('capture_location_explanation') or arrival.get('exception_reason')
    if unverified_capture:
        if not str(capture_explanation or '').strip(): errors.append('Explain why the evidence capture location could not be verified')
        else: reasons.append('Evidence location explanation: ' + str(capture_explanation))
    return dict(errors=errors, reasons=reasons, summary=summary, status='Needs review' if reasons else 'Submitted for normal review')
