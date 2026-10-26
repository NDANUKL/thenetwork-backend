"""Audited manual approvals and confirmations. Never sends money or calls a refund API."""
import hashlib
import json
import frappe
from fieldpulse.finance import (insert,position,earning,allocations,budget_for,request_for_offer,validate_offer_fx,
    require_notes,approve_stamp,independent,active_beneficiary,plain)
from fieldpulse.finance_documents import (require_enabled,require_finance,finance,lock,save_action,audit,
    private_proof,evidence_or_alternative,offer_terms,notify,review_hash)
from fieldpulse.finance_rules import money,positive,refund_allowed,conversion

TYPES={'DD Scout Offer','DD Scout Expense','DD Earning Adjustment','DD Payout Beneficiary','DD Scout Payout','DD Finance Cost','DD Customer Refund','DD Finance Case','DD Scout Earning'}


def lock_context(doc):
    keys=('scout','offer','project','request','payment','reversal_of')
    scope=tuple(doc.get(key) for key in keys)
    economics=review_hash(doc) if doc.doctype in {'DD Scout Payout','DD Customer Refund'} else None
    offers=[]
    if doc.doctype=='DD Scout Offer':offers=[doc]
    elif doc.get('offer'):offers=[frappe.get_doc('DD Scout Offer',doc.offer)]
    elif doc.doctype=='DD Scout Payout':offers=[frappe.get_doc('DD Scout Offer',row.offer) for row in doc.allocations]
    scout=doc.get('scout') or (offers[0].scout if offers else None)
    if scout:lock('Scout Profile',scout)
    references={request_for_offer(offer) for offer in offers}
    if doc.get('request'):references.add(doc.request)
    if doc.doctype=='DD Customer Refund':references.add(frappe.db.get_value('DD Payment',doc.payment,'request'))
    for reference in sorted(filter(None,references)):lock('Diaspora Request',reference)
    for project in sorted({offer.project for offer in offers}):lock('Field Request',project)
    for offer in sorted({offer.name for offer in offers}):lock('DD Scout Offer',offer)
    if doc.doctype=='DD Customer Refund':lock('DD Payment',doc.payment)
    if doc.get('reversal_of') and doc.doctype=='DD Scout Payout':lock('DD Scout Payout',doc.reversal_of)
    lock(doc.doctype,doc.name);doc.reload()
    if scope!=tuple(doc.get(key) for key in keys) or (economics and economics!=review_hash(doc)):
        frappe.throw('Financial details changed while obtaining approval locks. Refresh and review the current record.')


def payout_limits(doc):
    if doc.reversal_of:
        original=frappe.get_doc('DD Scout Payout',doc.reversal_of)
        if original.status!='Paid' or original.get('reversal_of') or original.scout!=doc.scout or original.currency!=doc.currency or original.beneficiary!=doc.beneficiary:frappe.throw('Reverse a confirmed original payout to the same recorded recipient/currency')
        for row in doc.allocations:
            limit=sum((money(r.amount) for r in original.allocations if r.offer==row.offer and r.kind==row.kind),money(0))
            for prior in frappe.get_all('DD Scout Payout',filters={'reversal_of':original.name,'name':['!=',doc.name],'status':['in',['Approved','Processing','Paid','On hold']]},fields=['name']):
                earlier=frappe.get_doc('DD Scout Payout',prior.name)
                limit-=sum((money(r.amount) for r in earlier.allocations if r.offer==row.offer and r.kind==row.kind),money(0))
            if money(row.amount)>limit:frappe.throw('Reversal exceeds the remaining original confirmed allocation')
        return
    for row in doc.allocations:
        offer=frappe.get_doc('DD Scout Offer',row.offer);p=position(offer,doc.name)
        if offer.status!='Accepted' or p['status']=='On hold':frappe.throw('Resolve the arrangement/payment hold before release')
        available=min(p['advance_available'],p['available']) if row.kind=='Travel advance' and earning(offer) else p['advance_available'] if row.kind=='Travel advance' else p['available']
        if row.kind=='Earning' and not earning(offer):frappe.throw('Work approval creates the entitlement; only agreed travel advances can precede it')
        if money(row.amount)>available:frappe.throw('Allocation exceeds the unreserved amount; another payment/advance may already be pending')


def payout_reviewers(doc):
    reviewers=[]
    for row in doc.allocations:
        offer=frappe.get_doc('DD Scout Offer',row.offer);entitlement=earning(offer)
        if entitlement:reviewers.append(entitlement.work_approved_by)
    return reviewers


@frappe.whitelist(methods=['POST'])
def act(doctype,name,action,data=None):
    require_enabled();require_finance()
    if doctype not in TYPES:frappe.throw('Unknown finance action target')
    data=frappe.parse_json(data) if isinstance(data,str) else data or {}
    if not isinstance(data,dict):frappe.throw('Invalid action data')
    doc=frappe.get_doc(doctype,name);doc.check_permission('write');lock_context(doc)
    before=doc.get('status')
    if doctype=='DD Scout Payout' and action=='Begin processing' and before=='Processing':return plain({'name':doc.name,'status':before})
    if doctype=='DD Scout Payout' and action=='Confirm paid' and before=='Paid':
        if str(data.get('reference') or '').strip()!=doc.reference or money(data.get('actual_amount'))!=money(doc.total):frappe.throw('This payout already has a different confirmed outcome')
        return plain({'name':doc.name,'status':before})
    if action=='Independent review':
        require_notes(data)
        if doctype not in {'DD Scout Payout','DD Customer Refund'} or doc.status not in {'Draft','Requested'}:frappe.throw('Independently review the final proposed amount/recipient/route before approval')
        conflict=frappe.session.user in payout_reviewers(doc) if doctype=='DD Scout Payout' else frappe.session.user==doc.owner
        if conflict:
            frappe.throw('The independent reviewer must be different from the work approver/requester')
        doc.independent_reviewer=frappe.session.user;doc.independent_review_at=frappe.utils.now_datetime();doc.independent_review_notes=data['notes'];doc.independent_review_hash=review_hash(doc)
    elif doctype=='DD Scout Offer':
        if action=='Issue':
            if doc.status!='Draft':frappe.throw('Issue a draft arrangement')
            validate_offer_fx(doc)
            if frappe.utils.getdate(doc.valid_until)<frappe.utils.getdate():frappe.throw('Set a valid acceptance deadline')
            if frappe.db.exists('DD Scout Offer',{'project':doc.project,'scout':doc.scout,'revisit':doc.revisit or ['is','not set'],'status':['in',['Issued','Accepted']],'name':['!=',doc.name]}):frappe.throw('A current arrangement already exists for this scout/project/revisit')
            doc.terms_hash=offer_terms(doc);doc.status='Issued'
            notify(doc.scout,'Scout fee arrangement ready','Open Earnings to read and accept your fee, travel conditions and payout terms before dispatch.',doc)
        elif action=='Bind existing assignment':
            require_notes(data)
            if doc.status!='Accepted' or doc.task:frappe.throw('Bind an accepted arrangement that has not been assigned')
            lock('Field Task',data.get('task'));task=frappe.get_doc('Field Task',data.get('task'))
            if task.field_request!=doc.project or task.scout_profile!=doc.scout or task.get('finance_offer') or task.status=='Cancelled':frappe.throw('Select this scout/project existing assignment without another arrangement')
            if doc.revisit:frappe.throw('Revisit arrangements bind through authorised revisit dispatch')
            doc.task=task.name;save_action(doc)
            previous=getattr(frappe.flags,'dd_finance_binding',None);frappe.flags.dd_finance_binding=task.name
            try:
                task.finance_offer=doc.name;task.save(ignore_permissions=True)
            finally:frappe.flags.dd_finance_binding=previous
        elif action=='Withdraw':
            require_notes(data)
            if doc.status not in {'Draft','Issued','Accepted'} or doc.task or any(a['status'] in {'Approved','Processing','Paid','On hold'} for a in allocations(doc)):frappe.throw('Bound/paid arrangements need a documented cancellation/compensation review')
            doc.status='Withdrawn';doc.decision_notes=data['notes'];notify(doc.scout,'Fee arrangement withdrawn',data['notes'],doc)
        else:frappe.throw('Choose Issue, Bind existing assignment or Withdraw')
    elif doctype=='DD Scout Expense':
        require_notes(data)
        if doc.status!='Submitted' or action not in {'Approve','Reject'}:frappe.throw('Review a submitted expense')
        if action=='Approve':evidence_or_alternative(doc,data);approve_stamp(doc)
        doc.status='Approved' if action=='Approve' else 'Rejected';doc.review_notes=data['notes']
        offer=frappe.get_doc('DD Scout Offer',doc.offer)
        notify(offer.scout,'Expense claim '+doc.status.lower(),'Your expense claim was '+doc.status.lower()+'. Open Earnings for its review details.',doc)
    elif doctype=='DD Earning Adjustment':
        if action!='Approve' or doc.status!='Draft':frappe.throw('Approve a draft adjustment; corrections use a new reversing adjustment')
        require_notes(data)
        if not earning(frappe.get_doc('DD Scout Offer',doc.offer)):frappe.throw('Approve compensation/work entitlement before adjusting it')
        if not doc.reason or not doc.authority_reference:frappe.throw('Record the agreement and lawful basis; no automatic tax rates/deductions are applied')
        evidence_or_alternative(doc,data)
        if doc.reversal_of:
            original=frappe.get_doc(doctype,doc.reversal_of)
            reversed_total=sum((money(row.amount) for row in frappe.get_all(doctype,filters={'reversal_of':original.name,'status':'Approved'},fields=['amount'])),money(0))
            if money(doc.amount)+reversed_total>money(original.amount):frappe.throw('Adjustment reversals exceed the original approved amount')
        doc.status='Approved';approve_stamp(doc)
        offer=frappe.get_doc('DD Scout Offer',doc.offer)
        notify(offer.scout,'Earnings adjustment approved','An approved adjustment changed your earnings. Open Earnings for the breakdown.',doc)
    elif doctype=='DD Payout Beneficiary':
        if doc.status!='Pending verification' or action not in {'Verify','Reject'}:frappe.throw('Review a pending recipient')
        require_notes(data)
        if action=='Verify':
            evidence_or_alternative(doc,data)
            if not doc.ownership_reference or doc.classification=='Not yet confirmed':frappe.throw('Verify recipient ownership and record supplier/employment classification before first payout')
            for old in frappe.get_all(doctype,filters={'scout':doc.scout,'status':'Verified'},fields=['name']):
                previous=frappe.get_doc(doctype,old.name);previous.status='Replaced';save_action(previous);audit(previous,'Recipient version replaced')
            doc.status='Verified';doc.verified_by=frappe.session.user;doc.verified_at=frappe.utils.now_datetime()
        else:doc.status='Rejected'
        notify(doc.scout,'Payout recipient '+doc.status.lower(),'Recipient '+doc.masked_account+' is '+doc.status.lower()+'. Existing processing payments were not redirected.',doc)
    elif doctype=='DD Scout Payout':
        if action=='Approve':
            if doc.status!='Draft':frappe.throw('Approve a draft payout')
            recipient=active_beneficiary(doc);payout_limits(doc);independent(doc,payout_reviewers(doc))
            doc.beneficiary_snapshot=recipient.account_holder+' | '+recipient.method+' | '+recipient.institution+' | '+recipient.masked_account
            doc.status='Approved';approve_stamp(doc)
        elif action=='Begin processing':
            if doc.status!='Approved':frappe.throw('Only an approved payment can enter processing; never resend an uncertain transfer')
            active_beneficiary(doc);payout_limits(doc);independent(doc,payout_reviewers(doc))
            doc.status='Processing';doc.processing_at=frappe.utils.now_datetime()
        elif action in {'Confirm paid','Confirm failed'}:
            if doc.status not in {'Processing','On hold'}:frappe.throw('Confirm the actual external outcome of a processing/held payment')
            require_notes(data);private_proof(doc,data.get('evidence'))
            if action=='Confirm paid':
                if data.get('recipient_matches') is not True or money(data.get('actual_amount'))!=money(doc.total):frappe.throw('Verify the actual amount and frozen recipient; a wrong recipient does not settle this scout')
                recipient=frappe.get_doc('DD Payout Beneficiary',doc.beneficiary)
                if not recipient.verified_by or not recipient.verified_at:frappe.throw('Recipient was not verified')
                independent(doc,payout_reviewers(doc));payout_limits(doc)
                reference=str(data.get('reference') or '').strip()
                if not reference:frappe.throw('Record the actual successful transaction/reversal reference')
                doc.reference_key=hashlib.sha256(reference.upper().encode()).hexdigest()
                doc.reference=reference;doc.status='Paid'
                notify(doc.scout,'Scout payment confirmed','A payment/reversal of '+str(doc.total)+' '+doc.currency+' was confirmed. Reference: '+reference+'. See Earnings for its task allocations.',doc)
            else:
                if data.get('failure_confirmed') is not True:frappe.throw('An uncertain outcome stays on hold/processing; verify actual failure before allowing another payment')
                doc.status='Failed'
            doc.confirmation_evidence=data['evidence'];doc.reconciliation_notes=data['notes'];doc.confirmed_at=frappe.utils.now_datetime();doc.hold_reason=None
        elif action=='Hold':
            require_notes(data)
            if doc.status not in {'Approved','Processing','On hold'}:frappe.throw('Hold an approved/processing payment')
            doc.status='On hold';doc.hold_reason=data['notes']
        elif action=='Cancel before execution':
            require_notes(data)
            if doc.status not in {'Draft','Approved'}:frappe.throw('Processing or uncertain payments need verified outcome confirmation, not cancellation/resending')
            doc.status='Failed';doc.reconciliation_notes='Cancelled before external execution: '+data['notes']
        else:frappe.throw('Choose a valid payout action')
        if action in {'Begin processing','Confirm failed','Hold','Cancel before execution'}:
            notify(doc.scout,'Payment '+doc.status.lower(),'Your payment status is '+doc.status.lower()+'. Open Earnings for details.',doc)
    elif doctype=='DD Finance Cost':
        if action!='Approve' or doc.status!='Draft':frappe.throw('Approve a draft actual cost')
        require_notes(data);evidence_or_alternative(doc,data);budget=budget_for(doc.request)
        conversion(doc.amount,doc.currency,budget.currency,doc.conversion_rate,doc.rate_date)
        doc.status='Approved';approve_stamp(doc)
    elif doctype=='DD Customer Refund':
        payment=frappe.get_doc('DD Payment',doc.payment)
        if action=='Approve':
            if doc.status!='Requested':frappe.throw('Approve a requested refund')
            require_notes(data)
            if data.get('provider_checked') is not True:frappe.throw('Check the merchant dashboard for prior refunds/chargebacks and confirm the original payment method first')
            alternative=doc.route=='Provider-approved alternative'
            if alternative:
                if not doc.provider_approval_reference or not doc.provider_approval_evidence or not doc.alternative_exposure_cleared:frappe.throw('Document provider approval and resolution of the original gateway/chargeback exposure')
                private_proof(doc,doc.provider_approval_evidence)
                if not doc.independent_reviewer or doc.independent_reviewer==frappe.session.user or doc.get('independent_review_hash')!=review_hash(doc):frappe.throw('A different Finance reviewer must approve the current exceptional amount/route')
            refund_allowed(payment,doc.amount,doc.original_method,doc.route,alternative_approved=alternative)
            doc.status='Approved';approve_stamp(doc)
        elif action=='Record provider pending':
            if doc.status!='Approved':frappe.throw('Record provider processing only after refund approval; a received request is not completion')
            require_notes(data)
            if not data.get('reference'):frappe.throw('Record the provider case/request reference')
            doc.provider_reference=data['reference'];doc.status='Provider pending'
        elif action in {'Confirm refund','Confirm failed'}:
            if doc.status!='Provider pending':frappe.throw('Confirm the actual outcome of the pending refund; do not resend an uncertain request')
            require_notes(data);private_proof(doc,data.get('evidence'))
            if action=='Confirm refund':
                if data.get('recipient_matches') is not True or money(data.get('actual_amount'))!=money(doc.amount):frappe.throw('Reconcile the actual amount and original/explicitly approved recipient')
                if data.get('credit_reference'):doc.credit_reference=data['credit_reference']
                if data.get('service_component') is not None:doc.service_component=float(money(data['service_component']))
                if data.get('conversion_rate') is not None:doc.conversion_rate=data['conversion_rate'];doc.rate_date=data.get('rate_date')
                if not doc.credit_reference:frappe.throw('Record the accounting credit document reference before confirming the refund')
                budget=budget_for(doc.request);conversion(doc.service_component or 0,doc.currency,budget.currency,doc.conversion_rate,doc.rate_date)
                doc.status='Confirmed';doc.confirmed_at=frappe.utils.now_datetime()
            else:
                if data.get('failure_confirmed') is not True:frappe.throw('Leave uncertain refunds pending until the provider confirms an outcome')
                doc.status='Failed'
            doc.confirmation_evidence=data['evidence']
        else:frappe.throw('Choose a valid refund action')
    elif doctype=='DD Finance Case':
        require_notes(data)
        if action=='Approve' and doc.status=='Proposed':doc.status='Approved';approve_stamp(doc)
        elif action=='Close' and doc.status=='Approved':doc.status='Closed'
        elif action=='Approve compensation' and doc.status=='Approved':
            lock('DD Scout Offer',data.get('offer'));offer=frappe.get_doc('DD Scout Offer',data.get('offer'))
            if request_for_offer(offer)!=doc.request or not offer.task or offer.status!='Accepted' or earning(offer):frappe.throw('Select an accepted bound arrangement without an existing entitlement; existing earnings use adjustments')
            private_proof(doc,data.get('evidence'))
            fee=money(data.get('fee') or 0);travel=money(data.get('travel') or 0)
            if fee+travel<=0:frappe.throw('Explicitly agree positive compensation; no fee is inferred from cancellation or a complaint')
            value=insert(frappe.get_doc(dict(doctype='DD Scout Earning',offer=offer.name,task=offer.task,financial_case=doc.name,currency=offer.currency,base_fee=float(fee),travel_entitlement=float(travel),work_approved_by=doc.approved_by,approved_at=frappe.utils.now_datetime(),due_date=frappe.utils.add_days(frappe.utils.getdate(),int(offer.due_days)))))
            position(offer);audit(value,'Compensation entitlement',{'case':doc.name,'evidence':data['evidence']})
            notify(offer.scout,'Compensation approved','A documented compensation decision has created an entitlement. Open Earnings for details and due date.',value)
        else:frappe.throw('Choose a valid case action/state')
    elif doctype=='DD Scout Earning':
        require_notes(data)
        if action not in {'Hold','Release hold'}:frappe.throw('Use Hold or Release hold')
        doc.on_hold=int(action=='Hold');doc.hold_reason=data['notes'] if doc.on_hold else None
        offer=frappe.get_doc('DD Scout Offer',doc.offer);notify(offer.scout,'Earnings hold updated',data['notes'],doc)
    else:frappe.throw('Unsupported finance action')
    save_action(doc)
    if doctype in {'DD Scout Expense','DD Earning Adjustment'}:position(frappe.get_doc('DD Scout Offer',doc.offer))
    audit(doc,action,{'from':before,'to':doc.get('status'),'notes':data.get('notes'),'evidence':data.get('evidence'),'reference':data.get('reference'),'actual_amount':data.get('actual_amount'),'service_component':data.get('service_component'),'credit_reference':data.get('credit_reference')})
    return plain({'name':doc.name,'status':doc.get('status'),'on_hold':doc.get('on_hold')})
