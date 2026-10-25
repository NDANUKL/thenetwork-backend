"""Project-only question edits; shared templates and dispatched versions stay immutable."""
import copy
import hashlib
import json
import re
from uuid import uuid4
from fieldpulse.scout_library import decode, resolve_config, validate_config, SHARED_V2, CLOSING_V2

EDIT_FIELDS = ('question','label','instructions','answer_format','answer_options','evidence_mode','evidence_json','configuration_json','check_key')
FORMATS = {'Single choice':'single','Multiple choice':'multi','Written answer':'text'}


def fingerprint(project):
    return hashlib.sha256(json.dumps(dict(template=project.get('scout_questionnaire'),
        brief=project.get('field_brief'), evidence=project.get('evidence_requirements'),
        context={key:project.get(key) for key in ('scout_authorisation','scout_reference_material','scout_contact_access','scout_restrictions')},
        checks=[{key:row.get(key) for key in EDIT_FIELDS} for row in project.get('scout_checks') or []]), sort_keys=True).encode()).hexdigest()


def validate_draft(project, questions):
    by_name={q.name:q for q in questions}
    seen=set()
    for row in project.get('scout_checks') or []:
        if not row.get('check_key'): row.check_key=str(uuid4())
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',row.check_key):raise ValueError('Invalid project question reference')
        if row.check_key in seen: raise ValueError('Each project question needs a unique reference')
        seen.add(row.check_key)
        source=by_name.get(row.get('question'))
        if row.get('question') and not source: raise ValueError('Choose template questions from this project\'s service')
        if not str(row.get('label') or '').strip() and source: row.label=source.label
        if not str(row.get('label') or '').strip(): raise ValueError('Write the question or remove its empty row')
        if len(row.label)>2000: raise ValueError('Keep each question under 2,000 characters')
        if not source and row.get('evidence_mode') in (None,'','Keep template evidence'):row.evidence_mode='Specify evidence'
        if not source and row.get('answer_format') in (None,'','Template format'): row.answer_format='Written answer'
        if source and row.get('answer_format') not in (None,'','Template format'):
            raise ValueError('Keep the template answer format, or replace this row with a new project question')
        if row.get('evidence_mode') not in (None,'','Keep template evidence','Specify evidence'):
            raise ValueError('Choose a valid evidence policy')
        if row.get('evidence_json'):
            value=decode(row.evidence_json,[])
            if not isinstance(value,list) or len(value)>20: raise ValueError('Choose up to 20 media requirements per question')
    if project.get('scout_checks_confirmed'): build_specs(project,questions)


def has_edits(project, questions):
    by_name={q.name:q for q in questions}
    for row in project.get('scout_checks') or []:
        source=by_name.get(row.get('question'))
        if not source or row.get('label') not in (None,'',source.label) or row.get('instructions') or row.get('evidence_mode')=='Specify evidence':return True
    return False


def evidence_rules(raw):
    result=[]
    for index,row in enumerate(decode(raw,[]) or [],1):
        if not isinstance(row,dict) or set(row)-{'id','kind','subject','when','once','detail_when','caption'}:raise ValueError('Invalid evidence settings')
        rule={key:copy.deepcopy(value) for key,value in row.items() if value not in (None,'',[])}
        rule.setdefault('id','project-media-'+str(index))
        if isinstance(rule.get('when'),str):rule['when']=[value.strip() for value in rule['when'].split('|') if value.strip()]
        result.append(rule)
    return result


def build_specs(project, questions):
    by_name={q.name:q for q in questions}
    if len({row.question for row in project.get('scout_checks') or [] if row.get('question')}) != sum(bool(row.get('question')) for row in project.get('scout_checks') or []):raise ValueError('Select a template question only once')
    selected={row.question for row in project.get('scout_checks') or [] if row.get('question')}
    mandatory={q.name for q in questions if (decode(q.get('validation_json'),{}) or {}).get('mandatory_evidence') or (decode(q.get('validation_json'),{}) or {}).get('mandatory_selection')}
    if not mandatory<=selected:raise ValueError('Retain the required visit-evidence question; edit its wording and capture subjects to suit the request')
    shared={q.question_code:q for q in questions if (decode(q.get('validation_json'),{}) or {}).get('group')=='shared'}
    authorization_required=any((decode(q.validation_json,{}) or {}).get('authorisation_required') for q in questions)
    if authorization_required and not str(project.get('scout_authorisation') or '').strip():raise ValueError('Record the service authorization before dispatch')
    specs=[]
    for shared_config in SHARED_V2:
        source=shared.get(shared_config['code'])
        config=decode(source.validation_json,{}) if source else {}
        if config.get('protocol_version')!=2:config=dict(shared_config,group='shared',protocol_version=2)
        specs.append(dict(code=shared_config['code'],label=source.label if source and (decode(source.validation_json,{}) or {}).get('protocol_version')==2 else shared_config['label'],help_text=source.get('help_text') or '' if source else '',config=config))
    for row in project.get('scout_checks') or []:
        source=by_name.get(row.get('question'))
        if source:
            original=decode(source.validation_json,{}) or {}
            if original.get('group')!='service':raise ValueError('Opening and closing checks are protected; edit only service questions')
            if original.get('protocol_version')==2:
                config=resolve_config(original,row.get('configuration_json'))
                if config is None:continue
            else:
                config=dict(group='service',protocol_version=2,answer_type='single',
                    result_options=original.get('result_options') or ['Observed','Confirmed','Partly confirmed','Not confirmed','Unable to check','Not applicable'],
                    text_required=True,evidence=[dict(id='visit-'+kind.lower(),kind=kind,subject=original.get('evidence_prompt') or 'Show the agreed site condition.') for kind in ('Photo','Video')] if original.get('mandatory_evidence') else [])
            code=source.question_code
        else:
            kind=FORMATS.get(row.get('answer_format') or 'Written answer')
            if not kind:raise ValueError('Choose Single choice, Multiple choice or Written answer')
            options=[value.strip() for value in str(row.get('answer_options') or '').splitlines() if value.strip()]
            if kind!='text' and (not 2<=len(options)<=30 or len(options)!=len(set(options))):raise ValueError('Provide 2 to 30 unique answer choices, one per line')
            config=dict(group='service',protocol_version=2,answer_type=kind,result_options=options if kind!='text' else [],text_required=True,evidence=[])
            code='P_'+str(row.check_key).replace('-','')[:24]
        original_rules=copy.deepcopy(config['evidence'])
        if row.get('evidence_mode')=='Specify evidence':
            config['evidence']=evidence_rules(row.get('evidence_json'))
            if source and source.name in mandatory:
                incoming={rule['id']:rule for rule in config['evidence']}
                for rule in original_rules:
                    replacement=incoming.get(rule['id'])
                    if not replacement or replacement.get('kind')!=rule['kind'] or replacement.get('when',[])!=rule.get('when',[]) or bool(replacement.get('once'))!=bool(rule.get('once')) or replacement.get('detail_when',[])!=rule.get('detail_when',[]):raise ValueError('Keep protected required media and conditions; its capture subject can be edited')
        if config.get('previous_required') and not project.get('scout_reference_material'):raise ValueError('Supply the previous report/reference material')
        if config.get('authorisation_required') and not project.get('scout_authorisation'):raise ValueError('Record the required authorization before dispatch')
        config.update(protocol_version=2,visit_workflow_version=2,source_basis_required=True)
        if authorization_required:config['authorisation_required']=True
        validate_config(config,assigned=True)
        specs.append(dict(code=code,label=row.label.strip(),help_text=row.get('instructions') or (source.get('help_text') or '' if source else ''),config=config))
    if not any(row['config']['group']=='service' for row in specs):raise ValueError('Retain at least one service question')
    specs.append(dict(code='S_EXTRA',label=CLOSING_V2['label'],help_text='',config=dict(CLOSING_V2,protocol_version=2,group='final',visit_workflow_version=2)))
    if len({row['code'] for row in specs})!=len(specs):raise ValueError('Project question codes must be unique')
    return specs


def materialize(project, questions):
    import frappe
    specs=build_specs(project,questions)
    base=frappe.get_doc('FP Questionnaire',project.scout_questionnaire)
    identity=hashlib.sha256(json.dumps(dict(project=project.name,base=base.name,scope=project.get('field_brief'),title=project.get('project_title'),evidence=project.get('evidence_requirements'),questions=specs),sort_keys=True).encode()).hexdigest()
    name='DDP-'+hashlib.sha256(project.name.encode()).hexdigest()[:10]+'-'+identity[:16]
    frappe.db.sql('SELECT name FROM `tabField Request` WHERE name=%s FOR UPDATE',[project.name])
    if not frappe.db.exists('FP Questionnaire',name):
        code='DDP-'+hashlib.sha256(project.name.encode()).hexdigest()[:16]
        last=frappe.db.get_value('FP Questionnaire',{'questionnaire_code':code},'version',order_by='version desc') or 0
        doc=frappe.get_doc(dict(doctype='FP Questionnaire',questionnaire_code=code,title=('Project questionnaire - '+(project.get('project_title') or project.name))[:140],
            version=int(last)+1,status='Draft',service_code=base.service_code,schema_hash=identity,source_sha256=base.get('source_sha256'),
            project=project.name,base_questionnaire=base.name,description=project.get('field_brief') or ''))
        doc.insert(ignore_permissions=True,set_name=name)
        for index,row in enumerate(specs,1):
            frappe.get_doc(dict(doctype='FP Question',questionnaire=name,question_code=row['code'],label=row['label'],help_text=row['help_text'],
                question_type='service_check',required=int(row['config']['group']!='final'),active=1,sequence=index,
                validation_json=json.dumps(row['config']))).insert(ignore_permissions=True)
        doc.status='Published';doc.published_at=frappe.utils.now_datetime();doc.save(ignore_permissions=True)
    published=frappe.get_doc('FP Questionnaire',name)
    if published.status!='Published' or published.project!=project.name or published.base_questionnaire!=base.name or published.schema_hash!=identity:
        frappe.throw('This project questionnaire version is retired or inconsistent; review the project questions before dispatch')
    return published


def apply_custom_task(task, project, questions):
    if not has_edits(project,questions):return False
    import frappe
    from fieldpulse.scout_v2 import enabled,workflow_enabled,snapshot_context
    if not enabled() or not workflow_enabled():frappe.throw('Enable the compatible questionnaire and verified-visit workflow before dispatching edited questionnaires')
    if not task.get('location'):frappe.throw('Assign the verified site before dispatching a project questionnaire')
    private=materialize(project,questions)
    rows=frappe.get_all('FP Question',filters={'questionnaire':private.name,'active':1},fields=['name','question_code','label','help_text','question_type','required','validation_json'],order_by='sequence asc')
    task.questionnaire=private.name;task.questionnaire_version=private.version
    task.questionnaire_scope=json.dumps([q.question_code for q in rows])
    site=frappe.get_doc('FP Location',task.location)
    snapshot=dict(task_scope=project.get('field_brief'),service=project.get('scout_service'),site_or_item=project.get('project_title'),
        evidence_tasks=project.get('evidence_requirements'),protocol_version=2,visit_workflow_version=2,resolved_questions=[dict(q) for q in rows],
        project_questionnaire=dict(version=1,source=project.scout_questionnaire,questionnaire=private.name,hash=private.schema_hash),
        site_reference={key:site.get(key) for key in ('location_name','address','latitude','longitude','geofence_radius_m')},**snapshot_context(project))
    if project.get('diaspora_request'):
        source=frappe.get_doc('Diaspora Request',project.diaspora_request)
        snapshot['client_request']=source.original_brief
        rounds=frappe.get_all('DD Request Details',filters={'request':source.name,'status':['in',['Ready for review','Closed']]},pluck='name',order_by='creation asc')
        snapshot['clarifications']=[{'question':q.question,'answer':q.answer} for name in rounds for q in frappe.get_doc('DD Request Details',name).questions]
    snapshot['questionnaire_review']=review_snapshot(project,api=frappe)
    task.client_request_snapshot=json.dumps(snapshot,default=str)
    return True


def review_snapshot(project, api=None):
    quote = api.db.get_value('DD Quotation', {'request':project.diaspora_request,'status':'Accepted'}, ['name','version'], as_dict=True) if api and project.get('diaspora_request') else None
    return dict(scope_reference=quote.get('name') if quote else None,scope_version=quote.get('version') if quote else None,
        reviewed_by=project.get('scout_checks_reviewed_by'),reviewed_at=str(project.get('scout_checks_reviewed_at') or ''),
        fingerprint=fingerprint(project),scope=project.get('field_brief'),template=project.get('scout_questionnaire'))


def editor_settings(project, question=None, configuration=None):
    import frappe
    doc=frappe.get_doc('Field Request',project)
    doc.check_permission('read')
    if not question:return dict(template=False,evidence=[])
    source=frappe.get_doc('FP Question',question)
    if source.questionnaire != doc.scout_questionnaire:frappe.throw('Choose a question from this project\'s template')
    row=next((row for row in doc.get('scout_checks') or [] if row.question==question),None)
    config=decode(source.validation_json,{})
    if config.get('protocol_version')==2:
        config=resolve_config(config,configuration if configuration is not None else row.get('configuration_json') if row else None) or config
    else:
        config=dict(result_options=config.get('result_options') or ['Observed','Confirmed','Partly confirmed','Not confirmed','Unable to check','Not applicable'],
            evidence=[dict(id='visit-'+kind.lower(),kind=kind,subject=config.get('evidence_prompt') or 'Show the agreed site condition.') for kind in ('Photo','Video')] if config.get('mandatory_evidence') else [])
    return dict(template=True,evidence=config.get('evidence') or [],options=config.get('result_options') or [],
        protected=bool((decode(source.validation_json,{}) or {}).get('mandatory_evidence') or (decode(source.validation_json,{}) or {}).get('mandatory_selection')))


def confirm(project, expected_modified):
    import frappe
    from fieldpulse.scout_submissions import require_reviewer
    require_reviewer()
    frappe.db.sql('SELECT name FROM `tabField Request` WHERE name=%s FOR UPDATE',[project])
    doc=frappe.get_doc('Field Request',project)
    doc.check_permission('write')
    if frappe.utils.get_datetime(doc.modified) != frappe.utils.get_datetime(expected_modified):frappe.throw('This questionnaire changed; reload and review before confirming')
    doc.scout_checks_confirmed=1
    doc.save()
    if not doc.scout_checks_confirmed:frappe.throw('Save your question edits before confirming the questionnaire')
    return dict(confirmed=True)
