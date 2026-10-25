"""Native DocType validation and append-only finance action boundary."""
from contextlib import contextmanager
import hashlib
import json
import frappe
from frappe.model.document import Document
from fieldpulse.finance_rules import money,positive,currency,conversion

INITIAL={'DD Scout Offer':'Draft','DD Scout Expense':'Draft','DD Earning Adjustment':'Draft',
 'DD Payout Beneficiary':'Pending verification','DD Scout Payout':'Draft','DD Finance Cost':'Draft',
 'DD Customer Refund':'Requested','DD Finance Case':'Proposed'}
COORDINATOR_READ={'DD Task Budget','DD Scout Offer','DD Scout Expense','DD Scout Earning','DD Customer Refund','DD Finance Case'}
SCOUT_READ={'DD Scout Offer','DD Scout Expense','DD Scout Earning','DD Earning Adjustment'}


def enabled():return getattr(frappe,'conf',{}).get('dd_finance_enabled') in (True,1,'1')
def finance(user=None):return bool({'Finance','System Manager'}.intersection(frappe.get_roles(user or frappe.session.user)))
def require_finance():
    if not finance():frappe.throw('Finance role required',frappe.PermissionError)
def require_enabled():
    if not enabled():frappe.throw('Finance operations are not enabled on this site')
def lock(dt,name):
    if dt not in {'Field Request','Field Task','Diaspora Request','DD Payment','Scout Profile','DD Scout Offer','DD Scout Expense','DD Scout Earning','DD Earning Adjustment','DD Payout Beneficiary','DD Scout Payout','DD Finance Cost','DD Customer Refund','DD Finance Case'}:raise ValueError('Unknown lock target')
    frappe.db.sql(f'SELECT name FROM `tab{dt}` WHERE name=%s FOR UPDATE',[name])
def internal(doc):return getattr(frappe.flags,'dd_finance_action',None) is doc
@contextmanager
def action_document(doc):
    previous=getattr(frappe.flags,'dd_finance_action',None);frappe.flags.dd_finance_action=doc
    try:yield
    finally:frappe.flags.dd_finance_action=previous
def save_action(doc):
    with action_document(doc):doc.save(ignore_permissions=True)
    return doc
def audit(doc,action,details=None):
    record=frappe.get_doc(dict(doctype='DD Finance Audit',reference_doctype=doc.doctype,reference_name=doc.name,
        action=action,actor=frappe.session.user,recorded_at=frappe.utils.now_datetime(),details=json.dumps(details or {},default=str)))
    with action_document(record):record.insert(ignore_permissions=True)
def notify(scout,subject,message,doc):
    user=frappe.db.get_value('Scout Profile',scout,'user')
    if user:frappe.get_doc(dict(doctype='Notification Log',for_user=user,from_user=frappe.session.user,type='Alert',subject=subject,email_content=frappe.utils.escape_html(message),document_type=doc.doctype,document_name=doc.name)).insert(ignore_permissions=True)
def own_scout():
    from fieldpulse.scout_self_service import _own_profile
    return _own_profile().name
def offer_for(doc):
    if doc.doctype=='DD Scout Offer':return doc
    return frappe.get_doc('DD Scout Offer',doc.offer)
def private_proof(doc,url):
    if not isinstance(url,str) or not url.startswith('/private/files/'):frappe.throw('Attach private confirmation evidence to this record')
    name=frappe.db.exists('File',{'file_url':url,'is_private':1})
    if not name:frappe.throw('Private evidence file not found')
    file=frappe.get_doc('File',name)
    if file.owner!=frappe.session.user and (file.attached_to_doctype!=doc.doctype or file.attached_to_name!=doc.name):frappe.throw('Evidence belongs to another record',frappe.PermissionError)
    return name
def evidence_or_alternative(doc,data):
    if doc.get('evidence'):private_proof(doc,doc.evidence)
    elif not (str(doc.get('alternative_evidence') or '').strip() and data.get('accept_alternative') is True):frappe.throw('Review receipts or explicitly authorise the recorded alternative evidence')
def offer_terms(doc):
    fields=('project','scout','revisit','currency','fee','travel_basis','travel_amount','advance_limit','expense_conditions','payout_terms','due_days','valid_until','conversion_rate','rate_date')
    return hashlib.sha256(json.dumps({k:doc.get(k) for k in fields},sort_keys=True,default=str).encode()).hexdigest()

def review_hash(doc):
    keys=('scout','beneficiary','currency','channel','reversal_of') if doc.doctype=='DD Scout Payout' else ('payment','currency','amount','original_method','route','reason','provider_approval_reference','provider_approval_evidence','alternative_exposure_cleared')
    values={key:doc.get(key) for key in keys}
    if doc.doctype=='DD Scout Payout':values['allocations']=[dict(offer=row.offer,kind=row.kind,amount=str(money(row.amount))) for row in doc.allocations]
    return hashlib.sha256(json.dumps(values,sort_keys=True,default=str).encode()).hexdigest()


def validate(doc):
    require_enabled()
    managed=internal(doc)
    previous=doc.get_doc_before_save() if not doc.is_new() else None
    if doc.doctype in {'DD Finance Audit','DD Scout Earning'}:
        if not managed:frappe.throw('This record is created only by its audited finance/work-approval action')
        return
    if not managed:
        require_finance()
        if previous and previous.get('status') and previous.status!=INITIAL.get(doc.doctype):frappe.throw('Financial terms/history are locked; use an audited action, reversal or new arrangement')
        for field in doc.meta.fields:
            if field.fieldname=='status' and doc.get('status')==INITIAL.get(doc.doctype):continue
            same=previous and doc.get(field.fieldname)==previous.get(field.fieldname)
            if previous and field.fieldtype=='Datetime' and doc.get(field.fieldname) and previous.get(field.fieldname):same=frappe.utils.get_datetime(doc.get(field.fieldname))==frappe.utils.get_datetime(previous.get(field.fieldname))
            if field.read_only and doc.get(field.fieldname) and not same:
                frappe.throw('Use the finance actions to change '+field.label)
        if doc.doctype in INITIAL:doc.status=INITIAL[doc.doctype]
    if doc.get('currency'):currency(doc.currency)
    if doc.doctype=='DD Task Budget':
        quote=frappe.get_doc('DD Quotation',doc.quotation)
        if quote.request!=doc.request or quote.status not in {'Issued','Accepted'}:frappe.throw('Use an issued/accepted quotation for this request')
        doc.currency=quote.currency
        doc.net_service_revenue=float(money(quote.get('taxable_amount') if quote.get('taxable_amount') is not None else money(quote.total)-money(quote.get('vat_amount') or 0)))
        for row in doc.get('lines') or []:
            if row.project and frappe.db.get_value('Field Request',row.project,'diaspora_request')!=doc.request:frappe.throw('Budget project belongs to another request')
            if row.revisit and frappe.db.get_value('DD Revisit Request',row.revisit,'request')!=doc.request:frappe.throw('Budget revisit belongs to another request')
            conversion(row.amount,row.currency,doc.currency,row.conversion_rate,row.rate_date)
    elif doc.doctype=='DD Scout Offer':
        fee=money(doc.fee);money(doc.get('travel_amount') or 0);money(doc.get('advance_limit') or 0)
        if fee==0 and not doc.revisit:frappe.throw('An initial assignment needs an agreed positive fee; a zero-additional-fee revisit must reference its existing arrangement')
        if doc.travel_basis=='No travel' and (money(doc.get('travel_amount') or 0) or money(doc.get('advance_limit') or 0)):frappe.throw('No-travel arrangements cannot include travel amounts/advances')
        if money(doc.get('advance_limit') or 0)>money(doc.get('travel_amount') or 0):frappe.throw('Travel advance exceeds the agreed travel allowance/cap')
        if not 0<=int(doc.get('due_days') or 0)<=90:frappe.throw('Agree payout timing from 0 to 90 days after work approval')
        if doc.revisit:
            revisit=frappe.get_doc('DD Revisit Request',doc.revisit)
            if frappe.db.get_value('Field Task',revisit.task,'field_request')!=doc.project:frappe.throw('Revisit belongs to another project')
        if not all(str(doc.get(k) or '').strip() for k in ('expense_conditions','payout_terms')):frappe.throw('Record expense conditions and payout terms before dispatch')
    elif doc.doctype in {'DD Scout Expense','DD Earning Adjustment'}:
        offer=offer_for(doc);doc.currency=offer.currency
        if offer.status!='Accepted':frappe.throw('Use an accepted scout arrangement')
        positive(doc.amount)
        if doc.doctype=='DD Scout Expense' and doc.kind=='Travel' and offer.travel_basis!='Reimburse approved actuals':frappe.throw('Travel is already fixed or not assigned; do not claim it twice')
        if doc.doctype=='DD Earning Adjustment' and doc.reversal_of:
            original=frappe.get_doc(doc.doctype,doc.reversal_of)
            if original.status!='Approved' or original.offer!=doc.offer or original.kind!=doc.kind or original.get('reversal_of'):frappe.throw('Reverse an approved original adjustment from this arrangement')
    elif doc.doctype=='DD Payout Beneficiary':
        if not managed and previous:
            for key in ('scout','method','account_holder','institution','account_number'):
                if doc.get(key)!=previous.get(key):frappe.throw('Recipient identity changes require a new re-authenticated request')
        if not managed and doc.is_new():frappe.throw('Create recipients through the re-authenticated beneficiary request')
        if not managed and doc.is_new() and frappe.db.exists('DD Payout Beneficiary',{'scout':doc.scout,'status':['in',['Verified','Replaced']]}):frappe.throw('Recipient changes require re-authentication through the beneficiary-change action')
        number=doc.get_password('account_number',raise_exception=False) if not doc.is_new() else doc.get('account_number')
        if not number or len(number)<4:frappe.throw('Enter the actual recipient number/account')
        doc.masked_account='•••• '+number[-4:]
    elif doc.doctype=='DD Scout Payout':
        recipient=frappe.get_doc('DD Payout Beneficiary',doc.beneficiary)
        if recipient.scout!=doc.scout:frappe.throw('Recipient belongs to another scout')
        total=money(0);seen=set()
        for row in doc.get('allocations') or []:
            offer=frappe.get_doc('DD Scout Offer',row.offer)
            if offer.scout!=doc.scout or offer.currency!=doc.currency:frappe.throw('Allocate only this scout/currency; never combine currencies')
            key=(row.offer,row.kind)
            if key in seen:frappe.throw('Include each arrangement/component only once')
            seen.add(key);total+=positive(row.amount)
        if total<=0:frappe.throw('Allocate a positive payout amount')
        doc.total=float(total)
        if previous and previous.status=='Draft' and previous.get('independent_review_hash') and review_hash(doc)!=previous.independent_review_hash:
            for key in ('independent_reviewer','independent_review_at','independent_review_notes','independent_review_hash'):doc.set(key,None)
        if previous and previous.status!='Draft' and (doc.beneficiary!=previous.beneficiary or doc.currency!=previous.currency):frappe.throw('Never redirect an approved/processing payment; resolve it and create a new approved record')
    elif doc.doctype=='DD Finance Cost':
        positive(doc.amount)
        if doc.project and frappe.db.get_value('Field Request',doc.project,'diaspora_request')!=doc.request:frappe.throw('Cost project belongs to another request')
        if doc.revisit and frappe.db.get_value('DD Revisit Request',doc.revisit,'request')!=doc.request:frappe.throw('Cost revisit belongs to another request')
    elif doc.doctype=='DD Customer Refund':
        payment=frappe.get_doc('DD Payment',doc.payment);doc.request=payment.request;doc.currency=payment.currency
        if positive(doc.amount)>money(payment.amount):frappe.throw('Refund exceeds collected payment')
        if money(doc.get('service_component') or 0)>money(doc.amount):frappe.throw('Service credit exceeds the refund amount')
        if doc.dispute and frappe.db.get_value('DD Dispute',doc.dispute,'request')!=doc.request:frappe.throw('Issue belongs to another request')
        if previous and previous.status=='Requested' and previous.get('independent_review_hash') and review_hash(doc)!=previous.independent_review_hash:
            for key in ('independent_reviewer','independent_review_at','independent_review_notes','independent_review_hash'):doc.set(key,None)
    elif doc.doctype=='DD Finance Case':
        if doc.dispute and frappe.db.get_value('DD Dispute',doc.dispute,'request')!=doc.request:frappe.throw('Issue belongs to another request')
        if not all(str(doc.get(k) or '').strip() for k in ('decision','scout_compensation')):frappe.throw('State the financial effect and scout compensation; neither is inferred automatically')
        if doc.task:
            project=frappe.db.get_value('Field Task',doc.task,'field_request')
            if frappe.db.get_value('Field Request',project,'diaspora_request')!=doc.request:frappe.throw('Assignment belongs to another request')


class FinanceDocument(Document):
    def validate(self):
        try:validate(self)
        except ValueError as error:frappe.throw(str(error))
    def on_trash(self):frappe.throw('Finance history is retained. Use a reversal, withdrawal or adjustment instead of deletion.')


def record_permission(doc,user=None,ptype=None,**kwargs):
    user=user or frappe.session.user
    if finance(user):return None
    if doc.doctype in COORDINATOR_READ and 'Field Operations Coordinator' in frappe.get_roles(user):return None if ptype in (None,'read','select','report') else False
    if doc.doctype not in SCOUT_READ or ptype not in (None,'read','select'):return False
    scout=frappe.db.exists('Scout Profile',{'user':user})
    if not scout:return False
    offer=offer_for(doc)
    return None if offer.scout==scout and offer.status!='Draft' else False


def query_condition(user=None,doctype=None):
    user=user or frappe.session.user
    if finance(user):return ''
    if doctype in COORDINATOR_READ and 'Field Operations Coordinator' in frappe.get_roles(user):return ''
    scout=frappe.db.exists('Scout Profile',{'user':user})
    if not scout or doctype not in SCOUT_READ:return '1=0'
    value=frappe.db.escape(scout)
    if doctype=='DD Scout Offer':return f'`tabDD Scout Offer`.scout={value} AND `tabDD Scout Offer`.status!="Draft"'
    return f'`tab{doctype}`.offer IN (SELECT name FROM `tabDD Scout Offer` WHERE scout={value})'


def child_permission(doc,user=None,ptype=None,**kwargs):
    # Child allocations are changed only through a validated parent document.
    # Direct REST edits would bypass the parent's immutable payment state.
    return None if ptype in (None,'read','select') else False
