"""Native quotations, verified payments and dispatch authority; production behavior is authoritative."""
import json
import hashlib
import secrets
from urllib.parse import urlencode, quote as urlquote
import frappe
import requests
from frappe.utils import getdate, now_datetime
from fieldpulse.payment_rules import money, instalments, checkout_url, verified_status, quotation_totals

def roles(user=None):
    return frappe.get_roles(user or frappe.session.user)

def _provider(path, body=None, params=None):
    environment, _, key, secret, _, base = _config()
    cache_key = f'dd:pesapal:token:{environment}'
    token = frappe.cache.get_value(cache_key)
    if not token:
        response = requests.post(base + '/Auth/RequestToken', json={'consumer_key': key, 'consumer_secret': secret}, timeout=20)
        response.raise_for_status()
        data = response.json()
        if str(data.get('status')) != '200' or not data.get('token'):
            frappe.throw('Pesapal authentication failed')
        token = data['token']
        from datetime import datetime, timezone
        expires = datetime.fromisoformat(data['expiryDate'].replace('Z', '+00:00'))
        ttl = max(1, min(240, int((expires - datetime.now(timezone.utc)).total_seconds()) - 30))
        frappe.cache.set_value(cache_key, token, expires_in_sec=ttl)
    response = requests.request('POST' if body is not None else 'GET', base + path, json=body, params=params, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'}, timeout=25)
    if response.status_code == 401:
        frappe.cache.delete_value(cache_key)
    response.raise_for_status()
    data = response.json()
    if str(data.get('status')) != '200':
        frappe.throw('Pesapal could not complete this action')
    return data

def _config():
    settings = frappe.get_doc('DD Payment Settings')
    if not settings.enabled:
        frappe.throw('Payment checkout is not enabled yet')
    environment = settings.environment
    if environment not in ['sandbox', 'live']:
        frappe.throw('Select sandbox or live')
    origin = (settings.customer_origin or '').rstrip('/')
    local_return = environment == 'sandbox' and settings.allow_local_return and (origin in ['http://localhost:3000', 'http://127.0.0.1:3000'])
    if not local_return and (not origin.startswith('https://') or '/' in origin[8:] or '@' in origin or ('?' in origin) or ('#' in origin)):
        frappe.throw('Configure the HTTPS website origin in DD Payment Settings')
    key = settings.get_password(environment + '_consumer_key', raise_exception=False)
    secret = settings.get_password(environment + '_consumer_secret', raise_exception=False)
    if not key or not secret:
        frappe.throw('Configure Pesapal credentials in DD Payment Settings')
    notification = settings.get(environment + '_ipn_id')
    base = 'https://cybqa.pesapal.com/pesapalv3/api' if environment == 'sandbox' else 'https://pay.pesapal.com/v3/api'
    return (environment, origin, key, secret, notification, base)

def csrf():
    staff = 'System Manager' in roles() or 'Field Operations Coordinator' in roles()
    account = frappe.session.user if staff else _customer()
    doctype = 'User' if staff else 'DD Customer Account'
    token = secrets.token_hex(24)
    frappe.db.set_value(doctype, account, {'portal_csrf_hash': hashlib.sha256(token.encode()).hexdigest(), 'portal_csrf_expires': frappe.utils.add_to_date(now_datetime(), minutes=10)})
    frappe.db.commit()
    return {'csrf_token': frappe.session.data.get('csrf_token') or '', 'mutation_token': token}

def mutation_proof():
    staff = 'System Manager' in roles() or 'Field Operations Coordinator' in roles()
    account = frappe.get_doc('User', frappe.session.user) if staff else frappe.get_doc('DD Customer Account', _customer())
    token = frappe.form_dict.get('portal_csrf_token')
    if not isinstance(token, str) or len(token) != 48 or hashlib.sha256(token.encode()).hexdigest() != account.portal_csrf_hash or (not account.portal_csrf_expires) or (frappe.utils.get_datetime(account.portal_csrf_expires) < now_datetime()):
        frappe.throw('Refresh your account session before making changes', frappe.PermissionError)

def register_ipn():
    if 'System Manager' not in frappe.get_roles():
        frappe.throw('Not permitted', frappe.PermissionError)
    url = 'https://thenetwork.frappe.cloud/api/method/dd_payment_ipn'
    result = _provider('/URLSetup/RegisterIPN', {'url': url, 'ipn_notification_type': 'GET'})
    if not result.get('ipn_id'):
        frappe.throw('Pesapal did not return a notification ID')
    environment = _config()[0]
    frappe.db.set_value('DD Payment Settings', 'DD Payment Settings', environment + '_ipn_id', result['ipn_id'])
    return {'success': True, 'ipn_id': result['ipn_id'], 'url': url}

def _lock(doctype, name):
    frappe.db.sql(f'SELECT name FROM `tab{doctype}` WHERE name=%s FOR UPDATE', (name,))

def _customer():
    user = frappe.session.user
    if user == 'Guest' or not frappe.db.get_value('User', user, 'enabled'):
        frappe.throw('Please sign in', frappe.PermissionError)
    account = frappe.db.get_value('DD Customer Account', {'user': user, 'email_verified': 1}, 'name')
    if not account or 'DD Customer' not in frappe.get_roles(user):
        frappe.throw('Verified customer account required', frappe.PermissionError)
    from fieldpulse.beta_access import require_access
    require_access(account)
    return account

def _owned(reference):
    account = _customer()
    if not frappe.db.exists('Diaspora Request', {'name': reference, 'dd_customer_account': account}):
        frappe.throw('Request not found', frappe.PermissionError)
    return frappe.get_doc('Diaspora Request', reference)

def validate_quote(doc, method=None):
    previous = doc.get_doc_before_save()
    if previous and previous.status != 'Draft':
        frappe.throw('Issued quotations are locked; prepare a new quotation for changed scope')
    if doc.status not in ('Draft', 'Issued'):
        frappe.throw('Quotation status is managed by the payment service')
    if doc.get('accepted_by') or doc.get('accepted_at'):
        frappe.throw('Acceptance is recorded only through customer approval')
    request = frappe.get_doc('Diaspora Request', doc.request)
    request.check_permission('read')
    _lock('Diaspora Request', request.name)
    if doc.status == 'Issued' and frappe.db.exists('DD Quotation', {'request': doc.request, 'status': ['in', ['Issued', 'Accepted']], 'name': ['!=', doc.name or '']}):
        frappe.throw('A current quotation already exists; withdraw the unpaid quote before issuing a replacement')
    sequence_value_1 = (request.full_name, request.email)
    doc.customer_name = sequence_value_1[0]
    doc.customer_email = sequence_value_1[1]
    if doc.currency not in ('KES', 'USD', 'GBP', 'EUR'):
        frappe.throw('Unsupported quotation currency')
    if not doc.items or getdate(doc.valid_until) < getdate(doc.quotation_date):
        frappe.throw('Add projects and a valid quotation expiry')
    sequence_value_2 = (set(), money(0))
    seen = sequence_value_2[0]
    total = sequence_value_2[1]
    for item in doc.items:
        field = frappe.get_doc('Field Request', item.field_request)
        if field.diaspora_request != doc.request or field.name in seen:
            frappe.throw('Include each quoted project once, from this request')
        seen.add(field.name)
        count = item.get('planned_scouts')
        if isinstance(count, bool) or not count or float(count) != int(count) or (not 1 <= int(count) <= 20):
            frappe.throw('Enter a planned scout count from 1 to 20 for every project')
        if float(item.quantity) <= 0:
            frappe.throw('Quantity must be positive')
        item.project_title = field.project_title or field.request_type
        item.description = item.description or field.field_brief
        if not item.description:
            frappe.throw('Describe the agreed scope for every project')
        item.amount = float(money(money(item.rate) * money(item.quantity)))
        total += money(item.amount)
    if doc.status == 'Issued' and (not doc.terms):
        frappe.throw('Add the terms before issuing this quotation')
    try:
        totals = quotation_totals(total, doc.get('discount_type') or 'None', doc.get('discount_value') or 0,
            doc.get('vat_rate'), bool(doc.get('tax_inclusive')))
    except ValueError as exc:
        frappe.throw(str(exc))
    for key, value in totals.items():
        setattr(doc, key, float(value))
    total = totals['total']
    sequence_value_3 = instalments(total)
    deposit = sequence_value_3[0]
    balance = sequence_value_3[1]
    sequence_value_4 = (float(total), float(deposit), float(balance))
    doc.total = sequence_value_4[0]
    doc.deposit_amount = sequence_value_4[1]
    doc.balance_amount = sequence_value_4[2]
    doc.deposit_percent = 50
    doc.version = 1

def _quote(reference):
    name = frappe.db.get_value('DD Quotation', {'request': reference, 'status': ['in', ['Issued', 'Accepted']]}, 'name', order_by='creation desc')
    return frappe.get_doc('DD Quotation', name) if name else None

def _obligations(quote):
    return frappe.get_all('DD Payment', filters={'quotation': quote.name}, fields=['name', 'kind', 'amount', 'currency', 'status'], order_by='creation asc')

def _billing(request):
    quote = _quote(request.name)
    if not quote:
        return {'quote': None, 'payments': [], 'documents': []}
    projects = []
    for item in quote.items:
        scouts = frappe.get_all('Field Task', filters={'field_request': item.field_request, 'status': ['!=', 'Cancelled']}, pluck='scout_profile')
        projects.append({'project': item.field_request, 'title': item.project_title, 'scope': item.description, 'planned_scouts': item.get('planned_scouts'), 'assigned_scouts': len(set(scouts)), 'amount': float(item.amount)})
    payments = _obligations(quote)
    deposit_paid = any((p.kind == 'deposit' and p.status == 'Paid' for p in payments))
    for payment in payments:
        payment.amount = float(payment.amount)
        payment.can_pay = quote.status == 'Accepted' and payment.status != 'Paid' and (payment.kind == 'deposit' or (deposit_paid and request.status == 'Completed'))
    return {'quote': {'name': quote.name, 'version': quote.get('version') or 1, 'status': quote.status, 'currency': quote.currency, 'total': float(quote.total), 'subtotal': quote.get('subtotal'), 'discount_amount': quote.get('discount_amount'), 'discount_type': quote.get('discount_type'), 'discount_reason': quote.get('discount_reason'), 'discount_value': quote.get('discount_value'), 'vat_rate': quote.get('vat_rate'), 'vat_amount': quote.get('vat_amount'), 'taxable_amount': quote.get('taxable_amount'), 'tax_inclusive': quote.get('tax_inclusive'), 'download_url': '/api/customer/requests/' + urlquote(request.name, safe='') + '/quote', 'deposit_amount': quote.get('deposit_amount'), 'balance_amount': quote.get('balance_amount'), 'valid_until': quote.valid_until, 'terms': quote.terms, 'scope': '\n'.join((item.description for item in quote.items)), 'projects': projects, 'can_accept': quote.status == 'Issued' and bool(quote.get('deposit_amount')) and (getdate(quote.valid_until) >= getdate())}, 'payments': payments, 'documents': []}

def billing(reference=None):
    if reference:
        return {'billing': _billing(_owned(reference))}
    account = _customer()
    requests_ = frappe.get_all('Diaspora Request', filters={'dd_customer_account': account}, fields=['name', 'summary'], limit_page_length=200)
    return {'requests': [{'name': row.name, 'title': row.summary, 'billing': _billing(frappe.get_doc('Diaspora Request', row.name))} for row in requests_]}

def accept_quote(reference, quote, version, submission_id):
    request = _owned(reference)
    _lock('Diaspora Request', request.name)
    current = _quote(reference)
    if not current or current.name != quote or str(current.get('version') or 1) != str(version):
        frappe.throw('This quotation has changed')
    if current.status == 'Accepted':
        return {'success': True}
    if getdate(current.valid_until) < getdate() or not current.get('deposit_amount'):
        frappe.throw('This quotation needs to be reissued before acceptance')
    if not isinstance(submission_id, str) or not 1 <= len(submission_id) <= 100:
        frappe.throw('Invalid acceptance reference')
    frappe.db.set_value('DD Quotation', current.name, {'status': 'Accepted', 'accepted_by': frappe.session.user, 'accepted_at': now_datetime(), 'acceptance_reference': submission_id})
    for sequence_item_1 in zip(('deposit', 'balance'), instalments(current.total)):
        kind = sequence_item_1[0]
        amount = sequence_item_1[1]
        frappe.get_doc({'doctype': 'DD Payment', 'request': reference, 'quotation': current.name, 'kind': kind, 'amount': float(amount), 'currency': current.currency, 'status': 'Unpaid'}).insert(ignore_permissions=True)
    return {'success': True}

def checkout(reference, payment, submission_id, return_origin=None):
    request = _owned(reference)
    _lock('Diaspora Request', request.name)
    obligation = frappe.get_doc('DD Payment', payment)
    quote = _quote(reference)
    if not quote or quote.status != 'Accepted' or obligation.request != reference or (obligation.quotation != quote.name):
        frappe.throw('Payment does not belong to the accepted quotation', frappe.PermissionError)
    if obligation.status == 'Paid':
        frappe.throw('This payment is already complete')
    if obligation.kind == 'balance' and (request.status != 'Completed' or not frappe.db.exists('DD Payment', {'quotation': quote.name, 'kind': 'deposit', 'status': 'Paid'})):
        frappe.throw('The balance is payable after completion and verified deposit')
    sequence_value_1 = _config()
    environment = sequence_value_1[0]
    origin = sequence_value_1[1]
    dd = sequence_value_1[2]
    dd = sequence_value_1[3]
    notification = sequence_value_1[4]
    dd = sequence_value_1[5]
    if return_origin and return_origin != origin:
        if environment != 'sandbox' or return_origin not in ('http://localhost:3000', 'http://127.0.0.1:3000') or (not frappe.db.get_single_value('DD Payment Settings', 'allow_local_return')):
            frappe.throw('Checkout return origin is not authorised')
        origin = return_origin
    if obligation.currency not in ([value.strip() for value in (frappe.db.get_single_value('DD Payment Settings', 'enabled_currencies') or 'KES').split(',')] or ['KES']):
        frappe.throw('This currency has not been enabled for checkout')
    if not notification:
        frappe.throw('Register the Pesapal notification endpoint first')
    if not isinstance(submission_id, str) or not 1 <= len(submission_id) <= 100:
        frappe.throw('Invalid checkout reference')
    active = frappe.db.get_value('DD Payment Attempt', {'payment': payment, 'status': ['in', ['Creating', 'Pending', 'Review']]}, 'name')
    if active:
        attempt = frappe.get_doc('DD Payment Attempt', active)
        if attempt.environment != environment or not attempt.checkout_url:
            frappe.throw('An earlier checkout is being reconciled. Please contact support before retrying')
        return {'checkout_url': checkout_url(attempt.checkout_url, environment)}
    merchant_reference = 'DD-' + secrets.token_hex(16)
    attempt = frappe.get_doc({'doctype': 'DD Payment Attempt', 'payment': payment, 'merchant_reference': merchant_reference, 'environment': environment, 'amount': obligation.amount, 'currency': obligation.currency, 'status': 'Creating', 'submission_id': submission_id}).insert(ignore_permissions=True)
    frappe.db.commit()
    try:
        result = _provider('/Transactions/SubmitOrderRequest', {'id': merchant_reference, 'currency': obligation.currency, 'amount': float(obligation.amount), 'description': f'Diaspora Desk {obligation.kind}', 'notification_id': notification, 'callback_url': origin + '/dashboard/billing?' + urlencode({'payment_return': '1', 'request': reference}), 'billing_address': {'email_address': frappe.session.user}})
        if result.get('merchant_reference') != merchant_reference or not result.get('order_tracking_id'):
            raise ValueError('Unexpected provider order')
        url = checkout_url(result.get('redirect_url'), environment)
        _lock('DD Payment Attempt', attempt.name)
        attempt.reload()
        if attempt.tracking_id and attempt.tracking_id != result['order_tracking_id']:
            raise ValueError('Provider tracking conflict')
        frappe.db.set_value('DD Payment Attempt', attempt.name, {'tracking_id': result['order_tracking_id'], 'checkout_url': url, 'status': attempt.status if attempt.status in ('Paid', 'Reversed', 'Failed') else 'Pending'})
        return {'checkout_url': url}
    except Exception:
        _lock('DD Payment Attempt', attempt.name)
        attempt.reload()
        if attempt.status not in ('Paid', 'Reversed'):
            frappe.db.set_value('DD Payment Attempt', attempt.name, 'status', 'Review')
        frappe.db.commit()
        frappe.throw('Checkout needs reconciliation. Please contact support before retrying')

def _verify(attempt_name, tracking_id=None):
    attempt = frappe.get_doc('DD Payment Attempt', attempt_name)
    tracking_id = tracking_id or attempt.tracking_id
    if not tracking_id:
        return
    if attempt.environment != _config()[0]:
        frappe.throw('Configure the original payment environment to reconcile this attempt')
    data = _provider('/Transactions/GetTransactionStatus', params={'orderTrackingId': tracking_id})
    state = verified_status(data, attempt.merchant_reference, attempt.amount, attempt.currency)
    payment = frappe.get_doc('DD Payment', attempt.payment)
    _lock('Diaspora Request', payment.request)
    _lock('DD Payment', payment.name)
    attempt.reload()
    payment.reload()
    if attempt.status == 'Paid' and state in ('Pending', 'Failed'):
        return
    frappe.db.set_value('DD Payment Attempt', attempt.name, {'tracking_id': tracking_id, 'status': state, 'confirmation_code': data.get('confirmation_code'), 'verified_at': now_datetime()})
    if state == 'Paid':
        if payment.status == 'Paid' and payment.get('paid_attempt') != attempt.name:
            frappe.db.set_value('DD Payment Attempt', attempt.name, 'status', 'Review')
            return
        frappe.db.set_value('DD Payment', payment.name, {'status': 'Paid', 'paid_attempt': attempt.name, 'paid_at': now_datetime()})
    elif state == 'Reversed' and payment.get('paid_attempt') == attempt.name:
        frappe.db.set_value('DD Payment', payment.name, 'status', 'Reversed')

def ipn(OrderTrackingId=None, OrderMerchantReference=None, OrderNotificationType=None):
    if not isinstance(OrderTrackingId, str) or len(OrderTrackingId) > 100 or (not isinstance(OrderMerchantReference, str)) or (len(OrderMerchantReference) > 50):
        frappe.throw('Invalid notification')
    name = frappe.db.get_value('DD Payment Attempt', {'merchant_reference': OrderMerchantReference}, 'name')
    if not name:
        frappe.throw('Unknown payment')
    attempt = frappe.get_doc('DD Payment Attempt', name)
    if attempt.tracking_id and attempt.tracking_id != OrderTrackingId:
        frappe.throw('Payment reference mismatch')
    try:
        _verify(name, OrderTrackingId)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.response.update({'orderNotificationType': 'IPNCHANGE', 'orderTrackingId': OrderTrackingId, 'orderMerchantReference': OrderMerchantReference, 'status': 500})
        return
    frappe.response.update({'orderNotificationType': 'IPNCHANGE', 'orderTrackingId': OrderTrackingId, 'orderMerchantReference': OrderMerchantReference, 'status': 200})

def refresh(reference):
    _owned(reference)
    attempts = frappe.db.sql("SELECT a.name FROM `tabDD Payment Attempt` a\n        INNER JOIN `tabDD Payment` p ON a.payment=p.name\n        WHERE p.request=%s AND a.tracking_id IS NOT NULL AND a.status IN ('Pending','Review') LIMIT 10", (reference,), as_dict=True)
    for attempt in attempts:
        _verify(attempt.name)
    return {'success': True}

def reconcile():
    for row in frappe.get_all('DD Payment Attempt', filters={'status': ['in', ['Pending', 'Review']], 'tracking_id': ['is', 'set']}, pluck='name', limit_page_length=100, order_by='modified asc'):
        try:
            _verify(row)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title='Pesapal reconciliation failed', message=f'Review payment attempt {row}; provider verification did not complete.')

def require_deposit(doc, method=None):
    if not doc.field_request:
        return
    previous = doc.get_doc_before_save()
    entering = doc.is_new() or (previous and (previous.scout_profile != doc.scout_profile or previous.field_request != doc.field_request or (previous.status == 'Cancelled' and doc.status != 'Cancelled')))
    if not entering or doc.status == 'Cancelled':
        return
    reference = frappe.db.get_value('Field Request', doc.field_request, 'diaspora_request')
    if not reference:
        return
    _lock('Diaspora Request', reference)
    quote = _quote(reference)
    if not quote or quote.status != 'Accepted' or (not frappe.db.exists('DD Payment', {'quotation': quote.name, 'kind': 'deposit', 'status': 'Paid'})):
        frappe.throw('Accept the quotation and verify the 50% deposit before assigning scouts')
    paid_attempt = frappe.db.get_value('DD Payment', {'quotation': quote.name, 'kind': 'deposit', 'status': 'Paid'}, 'paid_attempt')
    environment = frappe.db.get_value('DD Payment Attempt', paid_attempt, 'environment') if paid_attempt else None
    if environment != 'live' and (not (environment == 'sandbox' and frappe.db.get_single_value('DD Payment Settings', 'allow_sandbox_dispatch') and frappe.db.get_value('Diaspora Request', reference, 'sandbox_testing'))):
        frappe.throw('A live verified deposit is required for dispatch; sandbox dispatch must be explicitly enabled on a test site')
    line = None
    for row in quote.items:
        if row.field_request == doc.field_request:
            line = row
            break
    if not line:
        frappe.throw('This project is not included in the paid quotation')
    scouts = set(frappe.get_all('Field Task', filters={'field_request': doc.field_request, 'name': ['!=', doc.name or ''], 'status': ['!=', 'Cancelled']}, pluck='scout_profile'))
    scouts.add(doc.scout_profile)
    if len(scouts) > int(line.planned_scouts):
        frappe.throw('Scout count exceeds the accepted quotation; review the agreed scope first')

def withdraw_quote(quote):
    document = frappe.get_doc('DD Quotation', quote)
    document.check_permission('write')
    _lock('Diaspora Request', document.request)
    document.reload()
    if document.status != 'Issued' or frappe.db.exists('DD Payment', {'quotation': document.name}):
        frappe.throw('Only an unaccepted quotation can be withdrawn; accepted work needs a reviewed amendment')
    frappe.db.set_value('DD Quotation', document.name, 'status', 'Withdrawn')
    return {'success': True}


@frappe.whitelist()
def download_quote(reference):
    request = _owned(reference)
    quote = _quote(request.name)
    if not quote:
        frappe.throw('Quotation is not available', frappe.DoesNotExistError)
    # Ownership is established above; customers need no general Desk print permission.
    from frappe.utils.pdf import get_pdf
    template = frappe.get_doc('Print Format', 'Diaspora Desk Quotation')
    html = frappe.render_template(template.html, {'doc': quote})
    content = get_pdf('<html><head><meta charset="utf-8"></head><body><div class="print-format">'
        + html + '</div></body></html>', options={'page-size': 'A4', 'margin-top': '15mm',
        'margin-bottom': '15mm', 'margin-left': '15mm', 'margin-right': '15mm'})
    frappe.response['type'] = 'download'
    frappe.response['filename'] = quote.name + '.pdf'
    frappe.response['filecontent'] = content
    frappe.response['display_content_as'] = 'attachment'
