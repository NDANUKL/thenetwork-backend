import importlib.util
from pathlib import Path
import sys
import types
import unittest
from html import escape
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]

class Row(dict):
    __getattr__ = dict.get


def load(path, frappe, utils):
    spec = importlib.util.spec_from_file_location('visibility_test_module', ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe': frappe, 'frappe.utils': utils}):
        spec.loader.exec_module(module)
    return module


class VisibilityTests(unittest.TestCase):
    def test_application_email_is_queued_and_escaped(self):
        frappe = MagicMock()
        frappe.utils.escape_html.side_effect = escape
        branding = types.ModuleType('fieldpulse.email_branding')
        branding.render_email = lambda **kwargs: kwargs['body'] + kwargs['link'] + kwargs['label']
        branding.sender_address = lambda value: value
        frappe.get_all.side_effect = [['coordinator'], ['c@example.com', 'c@example.com']]
        module = load('fieldpulse/coordinator_notifications.py', frappe,
            types.SimpleNamespace(get_url_to_form=lambda *args: 'https://example.com/app/scout-application/APP'))
        with patch.dict(sys.modules, {'fieldpulse.email_branding': branding}):
            module.application_received(Row(name='APP', full_name='<script>', county='A&B'))
        mail = frappe.sendmail.call_args.kwargs
        self.assertEqual(mail['subject'], 'New scout application')
        self.assertEqual(mail['recipients'], ['c@example.com'])
        self.assertTrue(mail['delayed'])
        self.assertIn('&lt;script&gt;', mail['message'])
        self.assertIn('A&amp;B', mail['message'])
        self.assertIn('https://example.com/app/scout-application/APP', mail['message'])
        self.assertIn('Review application', mail['message'])
        self.assertNotIn('Reset password', mail['message'])
        self.assertEqual(mail['reference_name'], 'APP')

    def test_client_alert_is_persisted_once_and_enqueued_after_commit(self):
        frappe = MagicMock()
        frappe.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
        record = MagicMock()
        record.insert.return_value = record
        frappe.get_doc.return_value = record
        module = load('fieldpulse/coordinator_notifications.py', frappe,
            types.SimpleNamespace(get_url_to_form=lambda *args: ''))
        account = Row(name='ACCOUNT-1', beta_access='Pending')
        module.client_application_received(account)
        module.client_application_received(account)
        self.assertEqual(frappe.get_doc.call_count, 2)
        self.assertEqual(record.insert.call_count, 2)
        self.assertEqual(frappe.enqueue.call_count, 2)
        self.assertTrue(all(call.kwargs['enqueue_after_commit'] for call in frappe.enqueue.call_args_list))
        values = frappe.get_doc.call_args.args[0]
        self.assertEqual(values['doctype'], 'DD Coordinator Alert')
        self.assertEqual(values['reference_name'], 'ACCOUNT-1')

    def test_client_alert_skips_auto_approved_accounts(self):
        frappe = MagicMock()
        module = load('fieldpulse/coordinator_notifications.py', frappe,
            types.SimpleNamespace(get_url_to_form=lambda *args: ''))
        module.client_application_received(Row(name='ACCOUNT-1', beta_access='Approved'))
        frappe.get_doc.assert_not_called()
        frappe.enqueue.assert_not_called()

    def test_client_alert_recipients_and_account_link_are_scoped(self):
        frappe = MagicMock()
        branding = types.ModuleType('fieldpulse.email_branding')
        branding.render_email = lambda **kwargs: kwargs['body'] + kwargs['link'] + kwargs['label']
        branding.sender_address = lambda value: value
        frappe.get_all.side_effect = [['coordinator', 'disabled', 'website'],
            ['c@example.com', 'c@example.com', None]]
        frappe.db.exists.return_value = True
        frappe.utils.escape_html.side_effect = escape
        frappe.get_doc.side_effect = [Row(status='Pending', reference_name='ACCOUNT-1', attempts=0, name='ALERT-1', db_set=MagicMock()),
                                      Row(name='ACCOUNT-1', user='client@example.test'),
                                      Row(full_name='<Client>')]
        module = load('fieldpulse/coordinator_notifications.py', frappe,
            types.SimpleNamespace(get_url_to_form=lambda *args: 'https://example.com/app/dd-customer-account/ACCOUNT-1'))
        with patch.dict(sys.modules, {'fieldpulse.email_branding': branding}):
            module.send_client_application('ALERT-1')
        mail = frappe.sendmail.call_args.kwargs
        self.assertEqual(mail['recipients'], ['c@example.com'])
        self.assertEqual(mail['reference_doctype'], 'DD Customer Account')
        self.assertIn('&lt;Client&gt;', mail['message'])
        self.assertIn('Review client account', mail['message'])
        self.assertIn('https://example.com/app/dd-customer-account/ACCOUNT-1', mail['message'])
        self.assertEqual(frappe.get_all.call_args_list[1].kwargs['filters']['user_type'], 'System User')

    def test_client_alert_retry_and_delivery_failure_remain_recoverable(self):
        frappe = MagicMock()
        frappe.DoesNotExistError = type('DoesNotExistError', (Exception,), {})
        record = Row(status='Pending', reference_name='ACCOUNT-1', attempts=0, name='ALERT-1', next_attempt_at=None)
        record.db_set = MagicMock()
        frappe.get_doc.side_effect = [record, RuntimeError('temporary lookup failure')]
        frappe.db.exists.return_value = True
        frappe.get_all.return_value = ['ALERT-1']
        frappe.get_roles.return_value = []
        frappe.utils.now_datetime.return_value = '2026-11-17 10:00:00'
        frappe.utils.add_to_date.return_value = '2026-11-17 10:05:00'
        module = load('fieldpulse/coordinator_notifications.py', frappe,
            types.SimpleNamespace(get_url_to_form=lambda *args: ''))
        with patch.dict(sys.modules, {'fieldpulse.email_branding': types.SimpleNamespace(
                render_email=lambda **kwargs: kwargs['body'], sender_address=lambda value:value)}):
            module.send_client_application('ALERT-1')
        record.db_set.assert_any_call('attempts', 1, update_modified=False)
        record.db_set.assert_any_call('status', 'Pending', update_modified=False)
        frappe.log_error.assert_called_once()
        module.retry_client_applications()
        frappe.enqueue.assert_called_once_with('fieldpulse.coordinator_notifications.send_client_application',
            alert='ALERT-1', enqueue_after_commit=True)

    def test_report_uses_permissions_and_counts_allocations(self):
        frappe = MagicMock()
        frappe.get_roles.return_value = ['Field Operations Coordinator']
        frappe.get_list.side_effect = [
            [Row(name='T1', scout_profile='S1'), Row(name='T2', scout_profile='S1'), Row(name='T3', scout_profile='S2')],
            [Row(name='S1', scout_name='Scout One', base_county='Nairobi')]]
        module = load('fieldpulse/fieldpulse/report/county_assignment_balance/county_assignment_balance.py', frappe,
            types.SimpleNamespace(getdate=lambda x:x, add_days=lambda x,n:x))
        columns, rows, message, chart = module.execute()
        self.assertEqual(chart['data']['labels'], ['County unconfirmed', 'Nairobi'])
        self.assertEqual(chart['data']['datasets'][0]['values'], [1, 2])
        self.assertEqual(frappe.get_list.call_args_list[0].kwargs['filters']['status'], ['!=', 'Cancelled'])
        frappe.get_all.assert_not_called()
        self.assertEqual(rows[2]['scout_county'], 'County unconfirmed')

    def test_report_denies_non_coordinator(self):
        frappe = MagicMock()
        frappe.get_roles.return_value = ['Field Agent']
        frappe.PermissionError = PermissionError
        frappe.throw.side_effect = PermissionError
        module = load('fieldpulse/fieldpulse/report/county_assignment_balance/county_assignment_balance.py', frappe,
            types.SimpleNamespace(getdate=lambda x:x, add_days=lambda x,n:x))
        with self.assertRaises(PermissionError): module.execute()
        frappe.get_list.assert_not_called()
