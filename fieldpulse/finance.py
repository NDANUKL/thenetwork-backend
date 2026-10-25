"""Operational finance ledger. All money movement remains manual/external."""
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import frappe
from fieldpulse.finance_documents import (enabled,finance,require_finance,require_enabled,lock,
 action_document,save_action,audit,notify,own_scout,private_proof,evidence_or_alternative,offer_terms)
from fieldpulse.finance_rules import money,positive,conversion,earning_position,refund_allowed,margin,RESERVED


def plain(value):
    if isinstance(value,Decimal):return format(value,'.2f')
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [plain(v) for v in value]
    return value
def insert(doc):
    with action_document(doc):doc.insert(ignore_permissions=True)
    return doc
def request_for_offer(offer):return frappe.db.get_value('Field Request',offer.project,'diaspora_request')
def earning(offer):
    name=frappe.db.exists('DD Scout Earning',{'offer':offer.name})
    return frappe.get_doc('DD Scout Earning',name) if name else None
def allocations(offer,exclude=None):
    result=[]
    rows=frappe.get_all('DD Payout Allocation',filters={'offer':offer.name,'parenttype':'DD Scout Payout'},fields=['parent','kind','amount'],order_by='creation asc')
    for row in rows:
        if row.parent==exclude:continue
        payout=frappe.get_doc('DD Scout Payout',row.parent)
        result.append(dict(kind=row.kind,amount=row.amount,status=payout.status,currency=payout.currency,reversal_of=payout.get('reversal_of'),payout=payout.name,reference=payout.get('reference'),channel=payout.channel))
    return result
def position(offer,exclude=None):
    return earning_position(offer,earning(offer),
        frappe.get_all('DD Scout Expense',filters={'offer':offer.name},fields=['kind','status','amount','currency']),
        frappe.get_all('DD Earning Adjustment',filters={'offer':offer.name},fields=['kind','status','amount','currency','reversal_of']),allocations(offer,exclude))
def budget_for(reference):
    name=frappe.db.exists('DD Task Budget',{'request':reference})
    if not name:frappe.throw('Create the request cost budget before committing scout costs')
    return frappe.get_doc('DD Task Budget',name)
def validate_offer_fx(offer):
    budget=budget_for(request_for_offer(offer))
    return conversion(money(offer.fee)+money(offer.get('travel_amount') or 0),offer.currency,budget.currency,offer.get('conversion_rate'),offer.get('rate_date'))
def require_notes(data):
    if not str(data.get('notes') or '').strip():frappe.throw('Record the decision and supporting reason')
def approve_stamp(doc):doc.approved_by=frappe.session.user;doc.approved_at=frappe.utils.now_datetime()
def independent(doc,work_approvers):
    if frappe.session.user in set(work_approvers):
        from fieldpulse.finance_documents import review_hash
        if not doc.get('independent_reviewer') or doc.independent_reviewer==frappe.session.user or not doc.get('independent_review_notes') or doc.get('independent_review_hash')!=review_hash(doc):
            frappe.throw('The work approver also releases this money. A different Finance/System Manager must independently review this record first.')
def active_beneficiary(doc):
    recipient=frappe.get_doc('DD Payout Beneficiary',doc.beneficiary)
    if recipient.scout!=doc.scout or recipient.status!='Verified':frappe.throw('Use a current verified recipient; never redirect an existing processing payment')
    if frappe.db.exists('DD Payout Beneficiary',{'scout':doc.scout,'status':'Pending verification'}):frappe.throw('A recipient change is pending verification; resolve it before releasing money')
    return recipient


@frappe.whitelist()
def scout_earnings(start=0):
    scout=own_scout()
    if not enabled():return {'enabled':False,'as_of':frappe.utils.now_datetime(),'items':[],'offers':[]}
    try:start=int(start)
    except (ValueError,TypeError):frappe.throw('Invalid earnings history page')
    if start<0:frappe.throw('Invalid earnings history page')
    result=[];offers=[]
    rows=frappe.get_all('DD Scout Offer',filters={'scout':scout,'status':['in',['Issued','Accepted','Declined','Withdrawn']]},fields=['name'],order_by='creation desc, name desc',limit_start=start,limit_page_length=101)
    for row in rows[:100]:
        offer=frappe.get_doc('DD Scout Offer',row.name)
        task=frappe.get_doc('Field Task',offer.task) if offer.task else None
        agreement={k:offer.get(k) for k in ('name','project','revisit','status','currency','fee','travel_basis','travel_amount','advance_limit','expense_conditions','payout_terms','due_days','valid_until','accepted_at','terms_hash')}
        agreement['project_title']=frappe.db.get_value('Field Request',offer.project,'project_title')
        if offer.status!='Accepted':offers.append(agreement);continue
        entitlement=earning(offer);p=position(offer)
        recipient=frappe.db.get_value('DD Payout Beneficiary',{'scout':scout,'status':'Verified'},['masked_account','method'],as_dict=True)
        result.append(dict(agreement=agreement,assignment=offer.task,task_number=task.get('task_number') if task else None,
            **p,due_date=entitlement.get('due_date') if entitlement else None,
            hold_reason=entitlement.get('hold_reason') if entitlement and entitlement.on_hold else next((frappe.db.get_value('DD Scout Payout',a['payout'],'hold_reason') for a in allocations(offer) if a['status']=='On hold'),None),
            support=getattr(frappe,'conf',{}).get('dd_finance_support') or 'Contact your coordinator with the assignment and payment reference.',
            beneficiary=recipient,payments=[{k:a.get(k) for k in ('payout','kind','amount','status','reference','channel','reversal_of')} for a in allocations(offer)],
            entitlement_type='Compensation' if entitlement and entitlement.get('financial_case') else 'Work' if entitlement else None,
            compensation_terms=frappe.db.get_value('DD Finance Case',entitlement.financial_case,'scout_compensation') if entitlement and entitlement.get('financial_case') else None,
            expenses=frappe.get_all('DD Scout Expense',filters={'offer':offer.name},fields=['name','client_uuid','kind','amount','currency','status','description','alternative_evidence','review_notes']),
            adjustments=frappe.get_all('DD Earning Adjustment',filters={'offer':offer.name,'status':'Approved'},fields=['name','kind','amount','currency','reason','authority_reference','reversal_of'])))
    # Currency groups are intentional: there is no combined wallet balance.
    return plain(dict(enabled=True,as_of=frappe.utils.now_datetime(),items=result,offers=offers,
        next_start=start+100 if len(rows)>100 else None,
        beneficiary_pending=bool(frappe.db.exists('DD Payout Beneficiary',{'scout':scout,'status':'Pending verification'}))))


@frappe.whitelist(methods=['POST'])
def accept_offer(offer,decision,terms_hash):
    require_enabled();scout=own_scout();lock('DD Scout Offer',offer);doc=frappe.get_doc('DD Scout Offer',offer)
    if doc.scout!=scout:frappe.throw('This arrangement belongs to another scout',frappe.PermissionError)
    if doc.status=='Accepted' and decision=='Accept' and doc.terms_hash==terms_hash:return {'status':'Accepted'}
    if doc.status!='Issued' or decision not in {'Accept','Decline'}:frappe.throw('Respond to an issued arrangement')
    if doc.terms_hash!=terms_hash or offer_terms(doc)!=terms_hash:frappe.throw('The fee arrangement changed; refresh and read the current terms')
    if frappe.utils.getdate(doc.valid_until)<frappe.utils.getdate():frappe.throw('This offer expired; request a renewed arrangement')
    doc.status='Accepted' if decision=='Accept' else 'Declined';doc.accepted_by=frappe.session.user;doc.accepted_at=frappe.utils.now_datetime()
    save_action(doc);audit(doc,decision);return {'status':doc.status}


@frappe.whitelist(methods=['POST'])
def expense_draft(offer,client_uuid,kind,amount,description,alternative_evidence=None):
    require_enabled();scout=own_scout();arrangement=frappe.get_doc('DD Scout Offer',offer)
    if arrangement.scout!=scout or arrangement.status!='Accepted':frappe.throw('Use your accepted arrangement',frappe.PermissionError)
    if not isinstance(client_uuid,str) or not 8<=len(client_uuid)<=100:frappe.throw('A unique expense request ID is required')
    existing=frappe.db.exists('DD Scout Expense',{'client_uuid':client_uuid})
    if existing:
        doc=frappe.get_doc('DD Scout Expense',existing)
        if doc.offer!=offer:frappe.throw('Expense request belongs to another arrangement',frappe.PermissionError)
        if doc.kind!=kind or money(doc.amount)!=money(amount) or doc.description!=description or (doc.get('alternative_evidence') or '')!=(alternative_evidence or ''):
            frappe.throw('This expense request already records different details. Refresh its recorded claim before creating a correction.')
        return {'name':doc.name,'status':doc.status}
    doc=insert(frappe.get_doc(dict(doctype='DD Scout Expense',offer=offer,client_uuid=client_uuid,status='Draft',kind=kind,
        currency=arrangement.currency,amount=amount,description=description,alternative_evidence=alternative_evidence)))
    audit(doc,'Expense draft created');return {'name':doc.name,'status':doc.status}


@frappe.whitelist(methods=['POST'])
def submit_expense(expense,evidence=None):
    require_enabled();scout=own_scout();lock('DD Scout Expense',expense);doc=frappe.get_doc('DD Scout Expense',expense)
    if frappe.db.get_value('DD Scout Offer',doc.offer,'scout')!=scout:frappe.throw('Not your expense',frappe.PermissionError)
    if doc.status=='Submitted':return {'status':doc.status}
    if doc.status!='Draft':frappe.throw('Only a draft claim can be submitted')
    if evidence:private_proof(doc,evidence);doc.evidence=evidence
    if not doc.get('evidence') and not str(doc.get('alternative_evidence') or '').strip():frappe.throw('Attach a receipt or describe alternative evidence for approval')
    doc.status='Submitted';save_action(doc);audit(doc,'Expense submitted');return {'status':doc.status}


@frappe.whitelist(methods=['POST'])
def upload_expense_receipt(expense):
    import os
    require_enabled();scout=own_scout();lock('DD Scout Expense',expense);doc=frappe.get_doc('DD Scout Expense',expense)
    if doc.status!='Draft' or frappe.db.get_value('DD Scout Offer',doc.offer,'scout')!=scout:frappe.throw('Upload receipts only to your open expense claim',frappe.PermissionError)
    uploaded=frappe.request.files.get('file')
    if not uploaded:frappe.throw('Choose a receipt file')
    name=os.path.basename(uploaded.filename or 'receipt')
    if os.path.splitext(name)[1].lower() not in {'.pdf','.jpg','.jpeg','.png'}:frappe.throw('Use a PDF, JPEG or PNG receipt')
    content=uploaded.stream.read(10_000_001)
    if not content or len(content)>10_000_000:frappe.throw('Receipt must be nonempty and at most 10 MB')
    suffix=os.path.splitext(name)[1].lower()
    valid=content.startswith(b'%PDF-') if suffix=='.pdf' else content.startswith(b'\x89PNG\r\n\x1a\n') if suffix=='.png' else content.startswith(b'\xff\xd8\xff')
    if not valid:frappe.throw('Receipt content does not match its PDF/JPEG/PNG file type')
    from frappe.utils.file_manager import save_file
    file=save_file(name,content,doc.doctype,doc.name,is_private=1)
    return {'file_url':file.file_url}


def reauthenticate(password):
    from frappe.utils.password import check_password
    if not isinstance(password,str) or not password:frappe.throw('Re-enter your password for this sensitive action')
    check_password(frappe.session.user,password)


@frappe.whitelist(methods=['POST'])
def request_beneficiary(method,account_holder,institution,account_number,password,scout=None):
    require_enabled();reauthenticate(password)
    selected=scout if finance() and scout else own_scout()
    lock('Scout Profile',selected)
    if frappe.db.exists('DD Payout Beneficiary',{'scout':selected,'status':'Pending verification'}):frappe.throw('A recipient verification/change is already pending')
    doc=insert(frappe.get_doc(dict(doctype='DD Payout Beneficiary',scout=selected,status='Pending verification',method=method,
        account_holder=account_holder,institution=institution,account_number=account_number,classification='Not yet confirmed',reauthenticated_at=frappe.utils.now_datetime())))
    audit(doc,'Recipient requested',{'masked_account':doc.masked_account})
    notify(selected,'Payout recipient verification requested','A payout recipient was requested. Pending payments will not be redirected automatically. Contact Finance immediately if this was not you.',doc)
    return {'name':doc.name,'status':doc.status,'masked_account':doc.masked_account}


@frappe.whitelist(methods=['POST'])
def reveal_beneficiary(beneficiary,password):
    require_enabled();require_finance();reauthenticate(password);doc=frappe.get_doc('DD Payout Beneficiary',beneficiary)
    audit(doc,'Recipient details viewed after re-authentication')
    return {'account_holder':doc.account_holder,'institution':doc.institution,'method':doc.method,'account_number':doc.get_password('account_number')}


def dispatch_guard(task,method=None):
    if not enabled():return
    previous=task.get_doc_before_save() if not task.is_new() else None
    revisit=getattr(frappe.flags,'dd_authorized_revisit',None)
    if previous and previous.get('finance_offer') and previous.scout_profile!=task.scout_profile:
        frappe.throw('An agreed fee belongs to its scout. Create a separate authorised replacement assignment.')
    if previous and task.get('finance_offer')!=previous.get('finance_offer') and not revisit and getattr(frappe.flags,'dd_finance_binding',None)!=task.name:
        frappe.throw('Use the audited finance binding action to change the assignment arrangement')
    entering=task.is_new() or bool(revisit and previous and previous.status=='Awaiting authorization' and task.status=='In Progress')
    if not entering or task.status=='Cancelled':return
    reference=frappe.db.get_value('Field Request',task.field_request,'diaspora_request')
    if reference:assert_customer_open(reference,dispatch=True)
    lock('Field Request',task.field_request)
    filters={'project':task.field_request,'scout':task.scout_profile,'status':'Accepted','revisit':revisit or ['is','not set'],'task':['is','not set']}
    offers=frappe.get_all('DD Scout Offer',filters=filters,fields=['name'])
    if len(offers)!=1:frappe.throw('Record and obtain acceptance of exactly one scout fee/travel/payout arrangement before dispatch')
    offer=frappe.get_doc('DD Scout Offer',offers[0].name);lock('DD Scout Offer',offer.name)
    if offer.terms_hash!=offer_terms(offer):frappe.throw('Accepted fee terms changed; obtain a new acceptance')
    task.finance_offer=offer.name
    if not task.is_new():offer.task=task.name;save_action(offer);audit(offer,'Revisit bound to assignment')


def bind_offer(task,method=None):
    if not enabled() or not task.get('finance_offer'):return
    offer=frappe.get_doc('DD Scout Offer',task.finance_offer)
    if offer.task and offer.task!=task.name:frappe.throw('Accepted arrangement is already assigned')
    offer.task=task.name;save_action(offer);audit(offer,'Bound to assignment',{'task':task.name})


def work_approved(task,method=None):
    if not enabled() or task.status!='Approved':return
    for offer_row in frappe.get_all('DD Scout Offer',filters={'task':task.name,'status':'Accepted'},fields=['name','revisit']):
        lock('DD Scout Offer',offer_row.name)
        if frappe.db.exists('DD Scout Earning',{'offer':offer_row.name}):continue
        offer=frappe.get_doc('DD Scout Offer',offer_row.name)
        response=frappe.db.get_value('FP Task Response',{'task':task.name,'status':'Submitted','qa_status':'Passed'},'name',order_by='reviewed_at desc')
        if not response:frappe.throw('Approved work needs its coordinator review before creating entitlement')
        approved=frappe.get_doc('FP Task Response',response)
        if offer.revisit:
            revisit=frappe.get_doc('DD Revisit Request',offer.revisit)
            if revisit.status!='Dispatched':continue
            if frappe.utils.get_datetime(approved.reviewed_at)<frappe.utils.get_datetime(revisit.dispatched_at):continue
        doc=insert(frappe.get_doc(dict(doctype='DD Scout Earning',offer=offer.name,task=task.name,source_response=response,
            currency=offer.currency,base_fee=offer.fee,travel_entitlement=offer.travel_amount if offer.travel_basis=='Fixed allowance' else 0,
            work_approved_by=approved.reviewed_by,approved_at=approved.reviewed_at,
            due_date=frappe.utils.add_days(frappe.utils.getdate(approved.reviewed_at),int(offer.due_days)),on_hold=0)))
        audit(doc,'Entitlement created from work approval')
        notify(offer.scout,'Scout earnings approved','Your accepted work now has an earning entitlement. Open Earnings for the amount and due date. This does not depend on the customer paying the balance.',doc)


def assert_customer_open(reference,dispatch=False):
    if not enabled():return
    if frappe.db.exists('DD Finance Case',{'request':reference,'status':'Approved','pause_dispatch':1}):frappe.throw('Finance has paused new assignments/charges for this request; review its financial case')
    if dispatch:
        for payment in frappe.get_all('DD Payment',filters={'request':reference,'kind':'deposit','status':'Paid'},fields=['name','amount']):
            credited=sum((money(row.amount) for row in frappe.get_all('DD Customer Refund',filters={'payment':payment.name,'status':'Confirmed'},fields=['amount'])),money(0))
            if credited:frappe.throw('This deposit has been refunded in part or full; review a new approved funding arrangement before dispatch')


@frappe.whitelist()
def overview(request=None):
    require_enabled();require_finance()
    budgets=frappe.get_all('DD Task Budget',filters={'request':request} if request else {},fields=['name','request','quotation','currency','net_service_revenue'],limit_page_length=200)
    result=[]
    for row in budgets:
        budget=frappe.get_doc('DD Task Budget',row.name);planned=actual=credits=money(0)
        for line in budget.lines:planned+=conversion(line.amount,line.currency,budget.currency,line.conversion_rate,line.rate_date)
        projects=frappe.get_all('Field Request',filters={'diaspora_request':budget.request},pluck='name')
        arrangements=frappe.get_all('DD Scout Offer',filters={'project':['in',projects or ['__none__']],'status':'Accepted'},fields=['name'])
        liabilities=[]
        for selected in arrangements:
            offer=frappe.get_doc('DD Scout Offer',selected.name);p=position(offer)
            if earning(offer):actual+=conversion(p['gross_entitlement'],offer.currency,budget.currency,offer.get('conversion_rate'),offer.get('rate_date'))
            liabilities.append(dict(offer=offer.name,task=offer.task,scout=offer.scout,**p))
        for cost in frappe.get_all('DD Finance Cost',filters={'request':budget.request,'status':'Approved'},fields=['amount','currency','conversion_rate','rate_date']):actual+=conversion(cost.amount,cost.currency,budget.currency,cost.conversion_rate,cost.rate_date)
        for refund in frappe.get_all('DD Customer Refund',filters={'request':budget.request,'status':'Confirmed'},fields=['service_component','currency','conversion_rate','rate_date']):credits+=conversion(refund.service_component or 0,refund.currency,budget.currency,refund.conversion_rate,refund.rate_date)
        result.append(dict(name=budget.name,request=budget.request,currency=budget.currency,**margin(budget.net_service_revenue,planned,actual,credits),
            liabilities=liabilities,collections=frappe.get_all('DD Payment',filters={'request':budget.request},fields=['name','kind','currency','amount','status','paid_at']),
            refunds=frappe.get_all('DD Customer Refund',filters={'request':budget.request},fields=['name','currency','amount','status']),
            revisits=frappe.get_all('DD Revisit Request',filters={'request':budget.request},fields=['name','status','cost_arrangement','scout_compensation_reference']),
            cases=frappe.get_all('DD Finance Case',filters={'request':budget.request},fields=['name','kind','stage','status','pause_dispatch'])))
    return plain(dict(items=result,as_of=frappe.utils.now_datetime(),manual_execution=True))
