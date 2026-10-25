"""Commercial authorization precedes any actionable revisit or scout notification."""
import hashlib
import json
import frappe

ARRANGEMENTS = {'Existing agreement', 'Business-funded', 'Additional client charge'}
FROZEN = ('source_response', 'task', 'request', 'rework_questions_json', 'instructions',
    )
COMMERCIAL = ('assignment_choice', 'replacement_scout', 'reassignment_reason', 'scope_category', 'cost_arrangement', 'contract_reference',
    'client_acceptance_reference', 'scout_compensation_reference', 'authorization_notes')


def terms_hash(doc):
    return hashlib.sha256(json.dumps({key: doc.get(key) for key in (*FROZEN, *COMMERCIAL)}, sort_keys=True).encode()).hexdigest()


def validate_terms(doc):
    if doc.assignment_choice not in {'Same scout','Assign another scout'}: frappe.throw('Choose who will carry out the revisit')
    if doc.assignment_choice == 'Same scout' and (doc.get('replacement_scout') or doc.get('reassignment_reason')): frappe.throw('Clear replacement details when keeping the same scout')
    if doc.assignment_choice == 'Assign another scout' and (not doc.get('replacement_scout') or not str(doc.get('reassignment_reason') or '').strip()): frappe.throw('Choose a replacement scout and record the reason')
    if doc.cost_arrangement not in ARRANGEMENTS:
        frappe.throw('Choose and confirm the revisit cost arrangement')
    if doc.scope_category not in {'Existing agreed scope', 'Additional scope'}:
        frappe.throw('Identify whether this is existing or additional scope')
    for key, label in [('contract_reference', 'Contract / approved arrangement reference'),
        ('scout_compensation_reference', 'Scout compensation agreement reference'),
        ('authorization_notes', 'Authorization notes')]:
        if not str(doc.get(key) or '').strip(): frappe.throw(label + ' is required before authorization')
    if (doc.cost_arrangement == 'Additional client charge' or doc.scope_category == 'Additional scope') and not str(doc.get('client_acceptance_reference') or '').strip():
        frappe.throw('Record client acceptance of the additional scope/charge; do not create an automatic charge')
    # This is an authorization for the original pinned checks, never an implicit
    # amendment of scope. New checks require a separately agreed project scope.
    if doc.scope_category == 'Additional scope':
        frappe.throw('Additional scope requires the agreed scope/change-order process before a new assignment; this revisit can only repeat the original checks')


def validate_document(doc):
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    internal = frappe.flags.dd_revisit_action == doc.get('source_response')
    if doc.is_new() and not internal: frappe.throw('Create a revisit request from the submission review')
    if previous:
        for key in FROZEN:
            if doc.get(key) != previous.get(key): frappe.throw('Revisit instructions and source are frozen; scope amendments require a separate reviewed agreement')
        if not internal:
            for key in ('status', 'authorized_by', 'authorized_at', 'authorized_terms_hash', 'dispatched_by', 'dispatched_at', 'dispatched_task', 'decision_notes'):
                if doc.get(key) != previous.get(key): frappe.throw('Use the revisit authorization actions')
        if previous.status != 'Awaiting authorization' and not internal:
            if any(doc.get(key) != previous.get(key) for key in COMMERCIAL): frappe.throw('Authorized or closed revisit terms cannot be edited')


def create_request(task, response, reference, codes, notes, choice, scout, reason):
    existing = frappe.db.get_value('DD Revisit Request', {'source_response': response.name}, 'name')
    if existing: return existing
    doc = frappe.get_doc(dict(doctype='DD Revisit Request', source_response=response.name,
        task=task.name, request=reference, status='Awaiting authorization',
        rework_questions_json=json.dumps(codes), instructions=notes.strip(),
        assignment_choice=choice, replacement_scout=scout, reassignment_reason=reason,
        cost_arrangement='Pending decision', scope_category='Existing agreed scope'))
    marker = frappe.flags.dd_revisit_action
    frappe.flags.dd_revisit_action = response.name
    try: doc.insert(ignore_permissions=True)
    finally: frappe.flags.dd_revisit_action = marker
    frappe.db.set_value('Field Task', task.name, 'revisit_request', doc.name)
    return doc.name


def lock_request(name):
    # Match the review/dispatch lock order: customer request, task, revisit.
    reference = frappe.db.get_value('DD Revisit Request', name, 'request')
    task = frappe.db.get_value('DD Revisit Request', name, 'task')
    if reference: frappe.db.sql('SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE', [reference])
    frappe.db.sql('SELECT name FROM `tabField Task` WHERE name=%s FOR UPDATE', [task])
    frappe.db.sql('SELECT name FROM `tabDD Revisit Request` WHERE name=%s FOR UPDATE', [name])
    doc = frappe.get_doc('DD Revisit Request', name)
    doc.check_permission('write')
    return doc


@frappe.whitelist(methods=['POST'])
def act(revisit, action, notes=None):
    from fieldpulse.scout_submissions import require_reviewer
    require_reviewer()
    doc = lock_request(revisit)
    if action == 'Dispatch' and doc.status == 'Dispatched': return {'task': doc.dispatched_task, 'status': doc.status}
    if action == 'Authorize' and doc.status == 'Authorized': return {'status': doc.status}
    task = frappe.get_doc('Field Task', doc.task)
    source = frappe.get_doc('FP Task Response', doc.source_response)
    if task.status != 'Awaiting authorization' or source.qa_status != 'Failed' or source.task != task.name or source.agent != task.scout_profile:
        frappe.throw('This revisit is not awaiting an authorized dispatch')
    if action == 'Authorize':
        if doc.status != 'Awaiting authorization': frappe.throw('Authorize a pending revisit request')
        validate_terms(doc)
        doc.authorized_by = frappe.session.user
        doc.authorized_at = frappe.utils.now_datetime()
        doc.authorized_terms_hash = terms_hash(doc)
        doc.status = 'Authorized'
    elif action == 'Dispatch':
        if doc.status != 'Authorized': frappe.throw('Authorize the revisit before dispatch')
        validate_terms(doc)
        if not doc.authorized_by or doc.authorized_terms_hash != terms_hash(doc): frappe.throw('The authorized terms changed; record a new authorization')
        from fieldpulse.scout_rework import validate_assignment, create_revision, create_replacement
        scout = validate_assignment(task, 'Return to site', doc.assignment_choice, doc.replacement_scout, doc.reassignment_reason)
        profile = frappe.get_doc('Scout Profile', scout or task.scout_profile)
        if profile.availability_status == 'On Leave' or not profile.user or not frappe.db.get_value('User', profile.user, 'enabled'):
            frappe.throw('The receiving scout is unavailable or disabled; do not dispatch this revisit')
        codes = json.loads(doc.rework_questions_json)
        if scout:
            marker = frappe.flags.dd_authorized_revisit
            frappe.flags.dd_authorized_revisit = doc.name
            try: target = create_replacement(task, source, scout, doc.reassignment_reason, codes, doc.instructions)
            finally: frappe.flags.dd_authorized_revisit = marker
            frappe.db.set_value('Field Task', target.name, 'revisit_request', doc.name)
        else:
            target = task
            task.status = 'In Progress'
            task.submission_review_status = 'Revisit dispatched'
            task.submission_review_reasons = doc.instructions
            marker = frappe.flags.dd_authorized_revisit
            frappe.flags.dd_authorized_revisit = doc.name
            try: task.save(ignore_permissions=True)
            finally: frappe.flags.dd_authorized_revisit = marker
            revision = create_revision(source, task, 'Return to site')
            frappe.db.set_value('Field Task', task.name, 'rework_response', revision.name)
        from fieldpulse.scout_notifications import queue_rework
        queue_rework(target, source, 'Return to site', codes, doc.instructions)
        doc.status = 'Dispatched'
        doc.dispatched_task = target.name
        doc.dispatched_by = frappe.session.user
        doc.dispatched_at = frappe.utils.now_datetime()
    elif action in {'Return for changes', 'Reopen'}:
        expected = {'Authorized'} if action == 'Return for changes' else {'Declined', 'Cancelled'}
        if doc.status not in expected: frappe.throw('This revisit cannot be returned for changes from its current state')
        if not isinstance(notes, str) or not notes.strip(): frappe.throw('Explain why the authorization needs further review')
        doc.status = 'Awaiting authorization'
        doc.authorized_by = None
        doc.authorized_at = None
        doc.authorized_terms_hash = None
        doc.decision_notes = notes.strip()
        frappe.db.set_value('Field Task', task.name, {'submission_review_status': 'Awaiting revisit authorization', 'submission_review_reasons': 'Authorization review reopened: ' + notes.strip()})
    elif action in {'Decline', 'Cancel'}:
        if doc.status not in {'Awaiting authorization', 'Authorized'}: frappe.throw('Only a pending or authorized revisit can be closed')
        if not isinstance(notes, str) or not notes.strip(): frappe.throw('Record why the revisit is declined or cancelled')
        doc.status = 'Declined' if action == 'Decline' else 'Cancelled'
        doc.decision_notes = notes.strip()
        frappe.db.set_value('Field Task', task.name, {'submission_review_status': 'Revisit ' + doc.status.lower(), 'submission_review_reasons': 'Revisit ' + doc.status.lower() + ': ' + notes.strip()})
    else: frappe.throw('Choose a valid revisit action')
    marker = frappe.flags.dd_revisit_action
    frappe.flags.dd_revisit_action = doc.source_response
    try: doc.save(ignore_permissions=True)
    finally: frappe.flags.dd_revisit_action = marker
    return {'status': doc.status, 'task': doc.get('dispatched_task')}
