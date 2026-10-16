import frappe
from frappe.utils import now_datetime
from fieldpulse.payments import _customer as ddcustomer, _owned as ddowned, _lock as ddlock

@frappe.whitelist()
def disputes(reference=None):
    account = ddcustomer()
    filters = {'customer_account': account}
    if reference:
        ddowned(reference)
        filters['request'] = reference
    rows = frappe.get_all('DD Dispute', filters=filters, fields=['name', 'request', 'subject', 'reason', 'status', 'modified', 'response'], order_by='modified desc', limit_page_length=200)
    return {'disputes': rows}

@frappe.whitelist()
def create_dispute(reference, subject, reason, submission_id):
    request = ddowned(reference)
    ddlock('Diaspora Request', request.name)
    if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 140 or (not isinstance(reason, str)) or (not 20 <= len(reason.strip()) <= 4000):
        frappe.throw('Describe the issue with a subject and 20 to 4000 characters')
    if not isinstance(submission_id, str) or not 1 <= len(submission_id) <= 100:
        frappe.throw('Invalid dispute reference')
    existing = frappe.db.get_value('DD Dispute', {'request': reference, 'submission_id': submission_id}, 'name')
    if existing:
        return {'success': True, 'dispute': {'name': existing}}
    document = frappe.get_doc({'doctype': 'DD Dispute', 'request': reference, 'customer_account': ddcustomer(), 'subject': subject.strip(), 'reason': reason.strip(), 'submission_id': submission_id, 'status': 'Open'})
    document.insert(ignore_permissions=True)
    return {'success': True, 'dispute': {'name': document.name}}

def validate_dispute(doc):
    request = frappe.get_doc('Diaspora Request', doc.request)
    if request.dd_customer_account != doc.customer_account:
        frappe.throw('Dispute ownership does not match the request')
    previous = doc.get_doc_before_save()
    if not previous:
        if doc.status != 'Open' or doc.response:
            frappe.throw('New disputes must start Open, without a staff response')
    else:
        for key in ['request', 'customer_account', 'subject', 'reason', 'submission_id']:
            if doc.get(key) != previous.get(key):
                frappe.throw('Original dispute details cannot be replaced')
        transitions = {'Open': ['Under review', 'Awaiting customer', 'Resolved'], 'Under review': ['Awaiting customer', 'Resolved'], 'Awaiting customer': ['Under review', 'Resolved'], 'Resolved': ['Under review', 'Closed'], 'Closed': ['Under review']}
        if doc.status != previous.status and doc.status not in transitions.get(previous.status, []):
            frappe.throw('Invalid dispute transition')
        if doc.status in ['Resolved', 'Closed'] and (not (doc.response or '').strip()):
            frappe.throw('Provide the customer-visible resolution before resolving the dispute')
    events = []
    if previous:
        for event in previous.get('history') or []:
            events.append({'status': event.status, 'response': event.response, 'actor': event.actor, 'recorded_at': event.recorded_at})
    if not previous or previous.status != doc.status or previous.response != doc.response:
        events.append({'status': doc.status, 'response': doc.response, 'actor': frappe.session.user, 'recorded_at': now_datetime()})
    doc.set('history', events)
    if doc.status in ['Resolved', 'Closed']:
        doc.resolved_at = previous.resolved_at if previous and previous.resolved_at else now_datetime()

@frappe.whitelist()
def report(reference):
    ddowned(reference)
    name = frappe.db.get_value('DD Service Report', {'request': reference, 'status': 'Approved'}, 'name', order_by='creation desc')
    if not name:
        return {'report': None}
    doc = frappe.get_doc('DD Service Report', name)
    return {'report': {'name': name, 'title': doc.title, 'released': True, 'approved_at': doc.approved_at, 'download_url': '/api/customer/requests/' + reference + '/report'}}

@frappe.whitelist()
def download_report(reference):
    result = report(reference)
    if not result['report']:
        frappe.throw('An approved report is not yet available')
    doc = frappe.get_doc('DD Service Report', result['report']['name'])
    file_name = frappe.db.get_value('File', {'file_url': doc.report_file, 'is_private': 1}, 'name')
    if not file_name:
        frappe.throw('Private report file is unavailable')
    file = frappe.get_doc('File', file_name)
    frappe.response['type'] = 'download'
    frappe.response['filename'] = file.file_name
    frappe.response['filecontent'] = file.get_content()
    frappe.response['display_content_as'] = 'attachment'

def validate_report(doc):
    previous = doc.get_doc_before_save()
    if previous and previous.status == 'Approved':
        frappe.throw('Approved reports are locked; prepare a new version for corrections')
    if doc.status == 'Approved':
        if 'Field Operations Coordinator' not in frappe.get_roles() and 'System Manager' not in frappe.get_roles():
            frappe.throw('Only a coordinator can approve a report', frappe.PermissionError)
        if not doc.report_file or not frappe.db.exists('File', {'file_url': doc.report_file, 'is_private': 1}):
            frappe.throw('Attach a private report file before approval')
        file_name = frappe.db.get_value('File', {'file_url': doc.report_file, 'is_private': 1}, 'name')
        file = frappe.get_doc('File', file_name)
        if not file.file_name.lower().endswith('.pdf') or (file.file_size or 0) > 20000000:
            frappe.throw('Approved customer reports must be private PDF files up to 20 MB')
        if frappe.db.get_value('Diaspora Request', doc.request, 'status') != 'Completed':
            frappe.throw('Approve the field work and complete the request before approving its report')
        doc.approved_by = frappe.session.user
        doc.approved_at = now_datetime()

@frappe.whitelist()
def update_settings(full_name, phone, timezone, email_notifications):
    account = ddcustomer()
    if not isinstance(full_name, str) or not 1 <= len(full_name.strip()) <= 140 or (not isinstance(phone, str)) or (len(phone) > 30):
        frappe.throw('Enter a valid name and phone number')
    allowed = ['Africa/Nairobi', 'Europe/London', 'Europe/Paris', 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Asia/Dubai', 'Australia/Sydney', 'UTC']
    if timezone not in allowed or not isinstance(email_notifications, bool):
        frappe.throw('Invalid timezone or notification preference')
    user = frappe.get_doc('User', frappe.session.user)
    user.first_name = full_name.strip()
    user.last_name = ''
    user.time_zone = timezone
    user.mobile_no = phone.strip()
    user.save(ignore_permissions=True)
    frappe.db.set_value('DD Customer Account', account, 'email_notifications', int(email_notifications))
    return {'success': True, 'customer': {'id': account, 'email': user.email, 'full_name': user.full_name, 'phone': user.mobile_no, 'timezone': user.time_zone, 'email_verified': True, 'email_notifications': email_notifications}}

@frappe.whitelist()
def deletion_request(reason=''):
    account = ddcustomer()
    if not isinstance(reason, str) or len(reason) > 1000:
        frappe.throw('Reason must be at most 1000 characters')
    ddlock('DD Customer Account', account)
    name = frappe.db.get_value('DD Account Deletion', {'customer_account': account, 'status': ['in', ['Open', 'Under review']]}, 'name')
    if not name:
        doc = frappe.get_doc({'doctype': 'DD Account Deletion', 'customer_account': account, 'reason': reason, 'status': 'Open'}).insert(ignore_permissions=True)
        name = doc.name
    return {'success': True, 'reference': name}
