"""Reviewed recurring scopes; every occurrence enters the ordinary quote/payment workflow."""
from contextlib import contextmanager
from functools import wraps
from datetime import timedelta
import json
import frappe
from fieldpulse.recurring_rules import (schedule, digest, day, can_prepare, plan_transition,
    OPEN_PLANS, UNPREPARED, TERMINAL, LEAD_DAYS)

class RecurringError(ValueError):
    pass


def reject(message, permission=None):
    if permission: frappe.throw(message, permission)
    raise RecurringError(message)


def api(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        frappe.db.savepoint('recurring_api')
        try: return fn(*args, **kwargs)
        except RecurringError as error:
            frappe.db.rollback(save_point='recurring_api')
            return {'success':False,'error':str(error)}
    return wrapped


PLAN = 'DD Recurring Plan'
OCCURRENCE = 'DD Recurring Occurrence'
SOURCE_FIELDS = ('full_name','email','original_brief','summary','category','category_label',
    'assessment_status','classification_confidence','suggested_scouts','estimated_days','recommendation_reason',
    'coverage_note','needs_human_review','project_details','project_contract_version')
SITE_FIELDS = ('site_label','location_mode','county','area','map_url','latitude','longitude',
    'pin_type','contact_name','contact_phone','access_notes','project_ids')
CONTEXT = ('scout_authorisation','scout_reference_material',
    'scout_contact_access','scout_restrictions','field_brief','evidence_requirements')


@contextmanager
def writing():
    previous = frappe.flags.get('dd_recurring_write')
    frappe.flags.dd_recurring_write = True
    try: yield
    finally: frappe.flags.dd_recurring_write = previous


def validate_document(doc):
    if not frappe.flags.get('dd_recurring_write'):
        reject('Use the recurring-check actions; schedules, scope and history cannot be edited directly')


def staff():
    return bool({'System Manager','Field Operations Coordinator'}.intersection(frappe.get_roles()))


def require_staff():
    if not staff(): reject('Only coordinators may review or prepare recurring checks', frappe.PermissionError)


def account():
    from fieldpulse.payments import _customer
    return _customer()


def today():
    return day(frappe.utils.today())


def lock(doctype, name):
    if doctype not in (PLAN, OCCURRENCE, 'Diaspora Request'): raise ValueError('Invalid lock')
    frappe.db.sql('SELECT name FROM `tab' + doctype + '` WHERE name=%s FOR UPDATE', [name])


def owned_plan(name, customer=None):
    doc = frappe.get_doc(PLAN, name)
    if customer is not None:
        if doc.customer_account != customer: reject('Recurring plan not found', frappe.PermissionError)
    else:
        require_staff()
        doc.check_permission('read')
    return doc


def source_snapshot(source):
    from fieldpulse.project_alignment import project_plan
    from fieldpulse.task_briefs import validate_brief, brief_digest
    if source.status == 'Rejected' or (source.get('assessment_status') or source.category) in ('out_of_scope','needs_confirmation'):
        reject('This request needs an agreed supported scope before recurring checks can be set up')
    quote = frappe.db.get_value('DD Quotation', {'request': source.name, 'status': 'Accepted'}, ['name','version'], as_dict=True)
    if not quote: reject('Accept the source request quotation before setting up recurring checks')
    plan = project_plan(source)
    if plan['issues'] or not plan['projects'] or any(p['scope_status'] != 'supported' for p in plan['projects']):
        reject('Resolve the project scope before setting up recurring checks')
    projects = []
    operational_sites = []
    for item in plan['projects']:
        names = frappe.get_all('Field Request', filters={'diaspora_request': source.name, 'project_id': item['id'], 'status': ['!=','Cancelled']}, pluck='name')
        if len(names) != 1: reject('Every project needs one approved Task Brief')
        doc = frappe.get_doc('Field Request', names[0])
        if not doc.get('approved_task_brief'):
            reject('The coordinator must approve every project Task Brief first')
        brief = frappe.get_doc('DD Task Brief', doc.approved_task_brief)
        content = validate_brief(brief.content_json)
        if brief.project != doc.name or brief.status != 'Approved' or brief_digest(content) != brief.content_hash:
            reject('The approved Task Brief is inconsistent')
        if not doc.get('project_locations') or any(s.confirmation_status != 'Confirmed for dispatch' for s in doc.project_locations):
            reject('Confirm project locations before setting up recurring checks')
        operational_sites.extend(doc.project_locations)
        projects.append(dict(project_id=item['id'], **{key: doc.get(key) for key in CONTEXT},
            task_brief=content, brief_source=brief.name, fingerprint=brief.content_hash,
            reviewed_by=brief.approved_by, reviewed_at=str(brief.approved_at or '')))
    # Only scope inputs are copied. No task, answer, approval, invoice or payment is reused.
    values = {key: source.get(key) for key in SOURCE_FIELDS}
    sites = snapshot_sites(source.get('customer_sites') or [],operational_sites)
    if not sites: reject('Record the request locations before setting up recurring checks')
    values['customer_sites'] = sites
    for field, keys in [('evidence_checklist',('evidence_item','county','project_number')),
        ('risk_flags',('risk_flag',)), ('clarification_history',('question','answer'))]:
        values[field] = [{key: row.get(key) for key in keys} for row in source.get(field) or []]
    return dict(source=values, projects=projects, quote=dict(quote))


def snapshot_sites(source_sites, operational_sites):
    result=[]
    for original in source_sites:
        values={key:original.get(key) for key in SITE_FIELDS}
        matches=[row for row in operational_sites if row.get('source_site_id')==original.get('name')
            or (not row.get('source_site_id') and row.get('site_label')==original.get('site_label'))]
        overrides=[{key:row.get(key) for key in SITE_FIELDS if key!='project_ids'} for row in matches]
        if overrides and any(digest(row)!=digest(overrides[0]) for row in overrides):
            reject('A shared site has conflicting confirmed locations; resolve it before creating this plan')
        if overrides: values.update(overrides[0])
        result.append(values)
    return result


def finish_plan(doc):
    statuses=frappe.get_all(OCCURRENCE,filters={'plan':doc.name},pluck='status')
    if doc.status in ('Active','Paused') and statuses and all(status in TERMINAL for status in statuses):
        doc.status='Completed';record(doc,'Schedule finished')


def summary(doc):
    return {key: doc.get(key) for key in ('name','source_request','title','frequency','status','modified',
        'first_visit','last_visit','visit_count','window_days','review_notes','approved_at','service_category')}


def occurrence_data(row):
    return {key: row.get(key) for key in ('name','sequence','due_date','window_end','status','request',
        'access_notes','access_confirmed_at','decision_notes','modified')}


@frappe.whitelist()
@api
def eligibility(reference):
    from fieldpulse.payments import _owned
    source = _owned(reference)
    if source.get('recurring_plan'): return {'eligible':False,'reason':'This is an individual recurring visit. Manage its existing plan.','plan':source.recurring_plan}
    existing=frappe.db.get_value(PLAN,{'source_request':source.name,'status':['in',list(OPEN_PLANS)]},'name')
    if existing: return {'eligible':False,'reason':'This request already has an open recurring plan.','plan':existing}
    try: snapshot=source_snapshot(source)
    except (RecurringError, frappe.ValidationError):
        return {'eligible':False,'reason':'Accept the quotation and ask the coordinator to confirm the supported scope, Task Brief and precise locations first.'}
    return {'eligible':True,'title':source.summary,'brief':source.original_brief,
        'projects':len(snapshot['projects']),'quote':snapshot['quote']['name']}


@frappe.whitelist()
@api
def list_plans(page=1, reference=None):
    customer = account()
    page = max(1, min(1000, frappe.utils.cint(page)))
    filters = {'customer_account': customer}
    if reference:
        from fieldpulse.payments import _owned
        _owned(reference)
        filters['source_request'] = reference
    rows = frappe.get_all(PLAN, filters=filters, fields=['name'], order_by='creation desc', limit_start=(page-1)*20, limit_page_length=21)
    upcoming=[]
    for row in frappe.get_all(OCCURRENCE,filters={'customer_account':customer,'status':['in',['Awaiting access','Access confirmed']],
            'due_date':['<=',str(today()+timedelta(days=LEAD_DAYS))],'window_end':['>=',str(today())]},
            fields=['name','plan','due_date','window_end','status'],order_by='due_date asc',limit_page_length=100):
        if frappe.db.get_value(PLAN,row.plan,'status')=='Active': upcoming.append(dict(row))
    return {'plans': [summary(frappe.get_doc(PLAN, row.name)) for row in rows[:20]], 'has_more': len(rows)>20,'upcoming':upcoming}


@frappe.whitelist()
@api
def detail(plan):
    doc = owned_plan(plan, account())
    snapshot = json.loads(doc.scope_snapshot)
    rows = frappe.get_all(OCCURRENCE, filters={'plan': doc.name}, fields=['*'], order_by='sequence asc')
    return {'plan': summary(doc), 'brief': snapshot['source']['original_brief'],
        'questions': [{'project': p.get('field_brief'), 'questions': [q['label'] for q in p['checks']]} for p in snapshot['projects']],
        'occurrences': [occurrence_data(row) for row in rows]}


@frappe.whitelist(methods=['POST'])
@api
def create(reference, frequency, submission_id, start_date=None, visits=None, dates=None, window_days=6):
    from fieldpulse.payments import _owned
    source = _owned(reference)
    customer = account()
    lock('Diaspora Request', source.name)
    source.reload()
    if not isinstance(submission_id,str) or not 8 <= len(submission_id) <= 100: reject('Invalid submission reference')
    name = 'RCP-' + digest([customer, submission_id])[:32]
    existing = owned_plan(name, customer) if frappe.db.exists(PLAN, name) else None
    try:
        rows = schedule(frequency, start_date, visits, dates, window_days, day(str(existing.creation)[:10]) if existing else today())
    except ValueError as error: reject(str(error))
    payload_hash = digest(dict(reference=reference, frequency=frequency, rows=rows, window_days=window_days))
    if existing:
        if existing.creation_hash != payload_hash: reject('Use a new submission reference for changed dates')
        return {'success': True, 'plan': summary(existing)}
    if source.get('recurring_plan'): reject('Manage the original recurring plan rather than repeating an individual occurrence')
    if frappe.db.exists(PLAN, {'source_request': source.name, 'status': ['in',list(OPEN_PLANS)]}):
        reject('This request already has an open recurring plan; open Recurring checks to manage it')
    snapshot = source_snapshot(source)
    doc = frappe.get_doc(dict(doctype=PLAN, plan_key=name, source_request=source.name, customer_account=customer,
        title=(source.summary or source.name)[:140], service_category=source.get('category_label') or source.category, frequency=frequency, status='Pending review',
        scope_snapshot=json.dumps(snapshot,default=str), scope_hash=digest(snapshot), creation_hash=payload_hash,
        submission_id=submission_id, first_visit=rows[0]['due_date'], last_visit=rows[-1]['window_end'],
        visit_count=len(rows), window_days=window_days, history='[]'))
    with writing():
        doc.insert(ignore_permissions=True, set_name=name)
        for row in rows:
            frappe.get_doc(dict(doctype=OCCURRENCE, occurrence_key=occurrence_name(doc.name,row['sequence']), plan=doc.name, source_request=source.name,
                customer_account=customer, service_category=source.get('category_label') or source.category, status='Scheduled', history='[]', **row)).insert(ignore_permissions=True,
                    set_name=occurrence_name(doc.name,row['sequence']))
    return {'success': True, 'plan': summary(doc)}


def occurrence_name(plan, sequence):
    return 'RCO-' + digest([plan,sequence])[:32]


def record(doc, action, notes='', submission_id=None, payload_hash=None):
    history = json.loads(doc.history or '[]')
    history.append(dict(action=action, notes=notes, actor=frappe.session.user,
        at=str(frappe.utils.now_datetime()), id=submission_id, hash=payload_hash))
    doc.history = json.dumps(history)
    with writing(): doc.save(ignore_permissions=True)


def retry(doc, submission_id, payload):
    if not isinstance(submission_id,str) or not 8 <= len(submission_id) <= 100: reject('Invalid action reference')
    item = next((row for row in json.loads(doc.history or '[]') if row.get('id') == submission_id), None)
    if item and (item.get('hash') != digest(payload) or item.get('actor') != frappe.session.user):
        reject('Use a new action reference for changed instructions')
    return bool(item)


def check_version(doc, expected_modified):
    if not expected_modified or frappe.utils.get_datetime(doc.modified) != frappe.utils.get_datetime(expected_modified):
        reject('This recurring check changed. Refresh before continuing')


@frappe.whitelist(methods=['POST'])
@api
def act(plan, action, expected_modified, submission_id, occurrence=None, notes=''):
    # Customer and coordinator entry points are separate; website parameters cannot grant staff authority.
    return action_impl(plan, action, expected_modified, submission_id, occurrence, notes, customer=account())


@frappe.whitelist(methods=['POST'])
@api
def review(plan, action, expected_modified, submission_id, occurrence=None, notes=''):
    require_staff()
    return action_impl(plan, action, expected_modified, submission_id, occurrence, notes)


def action_impl(plan, action, expected_modified, submission_id, occurrence=None, notes='', customer=None):
    lock(PLAN, plan)
    doc = owned_plan(plan, customer)
    if not isinstance(notes,str) or len(notes)>2000: reject('Keep instructions under 2,000 characters')
    payload = dict(plan=plan,action=action,occurrence=occurrence,notes=notes)
    if occurrence:
        if not frappe.db.exists(OCCURRENCE, {'name': occurrence,'plan': doc.name}): reject('Visit not found')
        lock(OCCURRENCE, occurrence)
        visit = frappe.get_doc(OCCURRENCE, occurrence)
        if retry(visit,submission_id,payload): return {'success':True}
        check_version(visit,expected_modified)
        if action == 'Prepare' and customer is None:
            prepare_occurrence(doc,visit)
        elif action in ('Confirm access','Skip'):
            if doc.status != 'Active' or visit.status not in UNPREPARED or visit.get('request'):
                reject('Only unprepared visits in an active plan can be changed here')
            if today()>day(visit.window_end): reject('This visit window has passed; ask the coordinator about a new date')
            if action == 'Skip':
                if len(notes.strip())<3: reject('Give a reason for skipping this visit')
                visit.status='Skipped'; visit.decision_notes=notes.strip()
            else:
                if today()<day(visit.due_date)-timedelta(days=LEAD_DAYS): reject('Confirm access within 14 days of the visit')
                visit.access_notes=notes.strip(); visit.access_confirmed_at=frappe.utils.now_datetime()
                visit.access_confirmed_by=frappe.session.user; visit.status='Access confirmed'
        else: reject('Invalid recurring visit action')
        record(visit,action,notes,submission_id,digest(payload))
        if action=='Skip': finish_plan(doc)
    else:
        if retry(doc,submission_id,payload): return {'success':True}
        check_version(doc,expected_modified)
        if action in ('Approve','Decline') and customer is None and len(notes.strip())<10:
            reject('Record the schedule and commercial review decision')
        try: target=plan_transition(doc.status,action,staff=customer is None)
        except ValueError as error: reject(str(error))
        if action=='Approve':
            if day(doc.first_visit)<today(): reject('The first visit has passed; decline and request a new schedule')
            current=source_snapshot(frappe.get_doc('Diaspora Request',doc.source_request))
            if digest(current)!=doc.scope_hash: reject('The source scope changed; decline this plan and create it again from the confirmed request')
            doc.approved_by=frappe.session.user;doc.approved_at=frappe.utils.now_datetime()
        doc.status=target
        if action in ('Approve','Decline'): doc.review_notes=notes.strip()
        record(doc,action,notes,submission_id,digest(payload))
        if action in ('Cancel','Decline'):
            for name in frappe.get_all(OCCURRENCE,filters={'plan':doc.name,'status':['in',list(UNPREPARED)]},pluck='name'):
                visit=frappe.get_doc(OCCURRENCE,name);visit.status='Cancelled';record(visit,'Plan '+('declined' if action=='Decline' else 'cancelled'),notes)
    return {'success':True}


def prepare_occurrence(plan, visit):
    if visit.get('request'): return visit.request
    if not can_prepare(plan.status,visit,today()): reject('Activate the plan and confirm access within the visit window before preparing it')
    snapshot=json.loads(plan.scope_snapshot)
    if digest(snapshot)!=plan.scope_hash: reject('The approved recurring scope is inconsistent')
    if any(not p.get('task_brief') for p in snapshot['projects']):
        reject('This historical recurring scope needs a new Task Brief plan')
    # User identity is read from the account, never accepted from the client payload.
    customer=frappe.get_doc('DD Customer Account',plan.customer_account)
    from fieldpulse.beta_access import require_access
    require_access(customer)
    if not customer.email_verified or not frappe.db.get_value('User',customer.user,'enabled'): reject('The customer account is not active')
    values=json.loads(json.dumps(snapshot['source']))
    details=json.loads(values.get('project_details') or '[]')
    for item in details:
        spec=next((p for p in snapshot['projects'] if p['project_id']==item.get('id')),None)
        if spec: item['task_brief']=spec['task_brief']
    values['project_details']=json.dumps(details)
    values.update(doctype='Diaspora Request',status='New',submission_id='recurring:'+visit.name,
        email=customer.user,dd_customer_account=plan.customer_account,
        recurring_plan=plan.name,recurring_occurrence=visit.name,recurring_source=plan.source_request,
        deadline_preference='specific',deadline_date=str(visit.window_end),customer_action_required=0)
    for site in values['customer_sites']:
        if visit.get('access_notes'): site['access_notes']=(site.get('access_notes') or '')+'\nFor this visit: '+visit.access_notes
        site['confirmation_status']='Needs confirmation';site['location_verified']=0
    request=frappe.get_doc(values)
    with writing(): request.insert(ignore_permissions=True)
    targets=frappe.get_all('Field Request',filters={'diaspora_request':request.name},pluck='name')
    if len(targets)!=len(snapshot['projects']): reject('Recurring project conversion is incomplete')
    for name in targets:
        target=frappe.get_doc('Field Request',name)
        spec=next((p for p in snapshot['projects'] if p['project_id']==target.project_id),None)
        if not spec: reject('Unexpected recurring project identity')
        for key in CONTEXT: target.set(key,spec.get(key))
        target.recurring_plan=plan.name
        with writing(): target.save(ignore_permissions=True)
        # A new visit gets its own draft and requires a fresh coordinator approval.
        from fieldpulse.task_briefs import validate_brief, brief_digest
        content=validate_brief(spec.get('task_brief'))
        if brief_digest(content)!=spec['fingerprint']:
            reject('The approved Task Brief changed; preparation needs coordinator review')
        drafts=frappe.get_all('DD Task Brief',filters={'project':target.name,'status':'Draft'},pluck='name')
        if drafts:
            brief=frappe.get_doc('DD Task Brief',drafts[0])
            if brief_digest(validate_brief(brief.content_json))!=spec['fingerprint']:
                reject('The new visit draft does not match the approved recurring scope')
        else:
            marker=frappe.flags.dd_initial_brief_project
            frappe.flags.dd_initial_brief_project=target.name
            try:
                frappe.get_doc(dict(doctype='DD Task Brief',project=target.name,status='Draft',
                    content_json=json.dumps(content))).insert(ignore_permissions=True)
            finally: frappe.flags.dd_initial_brief_project=marker
    visit.request=request.name;visit.status='Prepared'
    record(visit,'Prepared separate request')
    return request.name


def guard_request(doc, method=None):
    previous=doc.get_doc_before_save() if not doc.is_new() else None
    if not doc.get('recurring_plan') and not doc.get('recurring_occurrence') and not (previous and previous.get('recurring_plan')): return
    if not previous and not frappe.flags.get('dd_recurring_write'): reject('Prepare recurring visits through the recurring plan')
    if previous and any(doc.get(k)!=previous.get(k) for k in ('recurring_plan','recurring_occurrence','recurring_source')):
        reject('Recurring visit provenance cannot be changed')


def guard_project(doc, method=None):
    previous=doc.get_doc_before_save() if not doc.is_new() else None
    if previous and previous.get('recurring_plan') and any(doc.get(k)!=previous.get(k) for k in ('recurring_plan',)):
        reject('Recurring Task Brief provenance cannot be changed')
    if not doc.get('recurring_plan'): return
    if not previous or not previous.get('recurring_plan'):
        if not frappe.flags.get('dd_recurring_write'): reject('Prepare recurring projects through their plan')
    if frappe.db.get_value('Diaspora Request',doc.diaspora_request,'recurring_plan') != doc.recurring_plan:
        reject('Recurring project ownership does not match its source')
    plan=frappe.get_doc(PLAN,doc.recurring_plan)
    spec=next((p for p in json.loads(plan.scope_snapshot)['projects'] if p['project_id']==doc.project_id),None)
    if not spec or not spec.get('task_brief'):
        reject('This historical recurring scope needs a new Task Brief plan')
    if doc.get('approved_task_brief'):
        brief=frappe.get_doc('DD Task Brief',doc.approved_task_brief)
        if brief.content_hash!=spec['fingerprint']:
            reject('This visit uses the approved recurring scope. Changes need a newly assessed request')


def process_due():
    if not frappe.conf.get('dd_native_handover_approved'): return
    # Each visit is independent: one bad scope or account cannot roll back other plans.
    pending=frappe.db.sql('''SELECT o.name FROM `tabDD Recurring Occurrence` o
        JOIN `tabDD Recurring Plan` p ON p.name=o.plan
        WHERE p.status IN ('Active','Paused') AND o.status IN ('Scheduled','Awaiting access','Access confirmed')
        AND o.due_date<=%s ORDER BY o.modified ASC LIMIT 500''',
        [str(today()+timedelta(days=LEAD_DAYS))],as_dict=True)
    finished=frappe.db.sql('''SELECT DISTINCT o.name FROM `tabDD Recurring Occurrence` o
        LEFT JOIN `tabDD Service Report` r ON r.request=o.request AND r.status='Approved'
        JOIN `tabDiaspora Request` d ON d.name=o.request
        WHERE o.status='Prepared' AND (r.name IS NOT NULL OR d.status='Rejected') LIMIT 500''',as_dict=True)
    for name in [row.name for row in pending+finished]:
        try:
            frappe.db.savepoint('recurring_visit')
            plan_name=frappe.db.get_value(OCCURRENCE,name,'plan')
            lock(PLAN,plan_name);lock(OCCURRENCE,name)
            plan=frappe.get_doc(PLAN,plan_name);visit=frappe.get_doc(OCCURRENCE,name)
            if visit.status=='Prepared':
                if visit.request and frappe.db.exists('DD Service Report',{'request':visit.request,'status':'Approved'}):
                    visit.status='Completed';record(visit,'Report approved')
                elif visit.request and frappe.db.get_value('Diaspora Request',visit.request,'status')=='Rejected':
                    visit.status='Cancelled';visit.decision_notes='This visit request was closed. Review its request for the reason and any outstanding arrangements.';record(visit,'Visit request closed')
            elif plan.status in ('Active','Paused'):
                if today()>day(visit.window_end): visit.status='Missed';record(visit,'Visit window passed without preparation')
                elif plan.status=='Active' and today()>=day(visit.due_date)-timedelta(days=LEAD_DAYS):
                    if visit.status=='Scheduled': visit.status='Awaiting access';record(visit,'Access reminder')
                    if visit.status=='Awaiting access':
                        from fieldpulse.customer_notifications import queue_event
                        queue_event('recurring',visit)
                    if can_prepare(plan.status,visit,today()): prepare_occurrence(plan,visit)
            finish_plan(plan)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback(save_point='recurring_visit')
            frappe.log_error(title='Recurring visit needs review',message=frappe.get_traceback())
