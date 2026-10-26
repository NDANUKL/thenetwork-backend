app_name = 'fieldpulse'

app_title = 'FieldPulse'

app_publisher = 'FieldPulse Team'

app_description = 'Offline-first geo-coded task platform for field agents'

app_email = 'admin@example.com'

app_license = 'MIT'

fixtures = [{'dt': 'Role',
  'filters': [['role_name',
               'in',
               ['Field Agent',
                'Supervisor',
                'Admin',
                'Diaspora Website Integration',
                'Field Operations Coordinator', 'Finance']]]}]

after_install = 'fieldpulse.install.after_install'

doc_events = {'Diaspora Request': {'before_save': ['fieldpulse.customer_requests.validate_ownership',
                                      'fieldpulse.customer_requests.validate_locations',
                                      'fieldpulse.native_events.map_diaspora'],
                      'after_insert': 'fieldpulse.native_events.ensure_field_requests',
                      'on_update': 'fieldpulse.native_events.ensure_field_requests'},
 'Field Request': {'before_save': ['fieldpulse.customer_requests.copy_ownership',
                                   'fieldpulse.native_events.map_field_request', 'fieldpulse.scout_templates.prepare_project'],
                   'on_update': 'fieldpulse.native_events.sync_task_navigation'},
 'Field Task': {'before_save': ['fieldpulse.native_events.map_task',
                                'fieldpulse.native_events.require_deposit', 'fieldpulse.scout_templates.apply_to_task']},
 'User': {'on_update': 'fieldpulse.scout_registration.sync_user',
          'validate': ['fieldpulse.scout_access.validate_user', 'fieldpulse.customer_access.validate_user'],
          'on_trash': 'fieldpulse.scout_access.protect_identity',
          'before_rename': 'fieldpulse.scout_access.protect_identity'},
 'FP Agent': {'on_update': 'fieldpulse.scout_registration.sync_agent'}}

after_migrate = 'fieldpulse.payment_install.after_migrate'

scheduler_events = {'cron': {'*/5 * * * *': ['fieldpulse.native_events.reconcile', 'fieldpulse.access_notifications.retry_approvals']},
 'daily': ['fieldpulse.fieldpulse.doctype.scout_profile.scout_profile.refresh_activity_statuses']}

override_whitelisted_methods = {'dd_assign_project_scouts': 'fieldpulse.scout_assignment.assign_project',
 'dd_payments': 'fieldpulse.customer_payments.dispatch',
 'dd_customer_registration': 'fieldpulse.customer_accounts.registration',
 'dd_customer_requests': 'fieldpulse.customer_requests.requests',
 'dd_detail_notifications': 'fieldpulse.request_details.notifications',
 'dd_payment_ipn': 'fieldpulse.customer_payments.notification',
 'dd_scout_task_team': 'fieldpulse.scout_registration.task_team',
 'dd_assign_scouts_without_extra_columns': 'fieldpulse.scout_assignment.assign'}

extend_bootinfo = "fieldpulse.native_ownership.extend_bootinfo"

auth_hooks = ["fieldpulse.scout_access.validate_auth", "fieldpulse.customer_access.validate_auth"]
on_login = ["fieldpulse.scout_access.on_login", "fieldpulse.customer_access.on_login"]

has_permission = {"Scout Profile": "fieldpulse.scout_self_service.profile_permission"}


for _doctype in ("Field Task", "FP Task Response", "FP Question Response", "Field Evidence"):
    has_permission[_doctype] = "fieldpulse.scout_permissions.record_permission"
permission_query_conditions = {
    "Field Task": "fieldpulse.scout_permissions.task_query",
    "FP Task Response": "fieldpulse.scout_permissions.response_query",
    "FP Question Response": "fieldpulse.scout_permissions.answer_query",
    "Field Evidence": "fieldpulse.scout_permissions.evidence_query",
}

# Customer-facing milestones share one durable, preference-aware delivery queue.
for _notification_doctype in ("DD Request Details", "DD Quotation", "DD Payment", "DD Service Report", "DD Dispute"):
    doc_events.setdefault(_notification_doctype, {})["on_update"] = "fieldpulse.customer_notifications.capture"
scheduler_events["cron"]["*/5 * * * *"].extend(["fieldpulse.customer_notifications.retry_pending", "fieldpulse.scout_notifications.retry_pending"])

# Finance tracks task obligations/manual settlement; it does not replace Pesapal.
app_include_js = globals().get('app_include_js', []) + ['/assets/fieldpulse/js/finance_forms.js']
doc_events['Field Task']['before_save'].append('fieldpulse.finance.dispatch_guard')
_finance_existing_insert = doc_events['Field Task'].get('after_insert', [])
doc_events['Field Task']['after_insert'] = ([_finance_existing_insert] if isinstance(_finance_existing_insert,str) else _finance_existing_insert) + ['fieldpulse.finance.bind_offer']
doc_events['Field Task'].setdefault('on_update', []).append('fieldpulse.finance.work_approved')
for _finance_doctype, _finance_query in {
    'DD Task Budget':'budget', 'DD Scout Offer':'offer', 'DD Scout Expense':'expense',
    'DD Scout Earning':'earning', 'DD Earning Adjustment':'adjustment',
    'DD Payout Beneficiary':'beneficiary', 'DD Scout Payout':'payout',
    'DD Finance Cost':'cost', 'DD Customer Refund':'refund', 'DD Finance Case':'case',
    'DD Finance Audit':'audit',
}.items():
    has_permission[_finance_doctype]='fieldpulse.finance_documents.record_permission'
    permission_query_conditions[_finance_doctype]='fieldpulse.finance_permissions.'+_finance_query

for _finance_child in ('DD Payout Allocation','DD Budget Line'):
    has_permission[_finance_child]='fieldpulse.finance_documents.child_permission'

# Recurring scopes never bypass the existing quote, deposit, location or scout-pay gates.
doc_events['Diaspora Request']['before_save'].append('fieldpulse.recurring.guard_request')
doc_events['Field Request']['before_save'].append('fieldpulse.recurring.guard_project')
scheduler_events['cron']['*/5 * * * *'].append('fieldpulse.recurring.process_due')

doc_events.setdefault('DD Recurring Occurrence', {})['on_update']='fieldpulse.customer_notifications.capture'
