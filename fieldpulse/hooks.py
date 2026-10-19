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
                'Field Operations Coordinator']]]}]

after_install = 'fieldpulse.install.after_install'

doc_events = {'Diaspora Request': {'before_save': ['fieldpulse.customer_requests.validate_ownership',
                                      'fieldpulse.customer_requests.validate_locations',
                                      'fieldpulse.native_events.map_diaspora'],
                      'after_insert': 'fieldpulse.native_events.ensure_field_requests',
                      'on_update': 'fieldpulse.native_events.ensure_field_requests'},
 'Field Request': {'before_save': ['fieldpulse.customer_requests.copy_ownership',
                                   'fieldpulse.native_events.map_field_request'],
                   'on_update': 'fieldpulse.native_events.sync_task_navigation'},
 'Field Task': {'before_save': ['fieldpulse.native_events.map_task',
                                'fieldpulse.native_events.require_deposit']},
 'User': {'on_update': 'fieldpulse.scout_registration.sync_user'},
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

has_permission = {"Scout Profile": "fieldpulse.scout_self_service.profile_permission"}
