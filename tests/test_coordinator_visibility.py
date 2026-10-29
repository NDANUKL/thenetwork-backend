import importlib.util
from pathlib import Path
import sys
import types
import unittest
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
        from jinja2 import Environment, FileSystemLoader
        frappe = MagicMock()
        env = Environment(loader=FileSystemLoader(str(ROOT)))
        frappe.render_template.side_effect = lambda template, context: env.get_template(template).render(context)
        frappe.get_all.side_effect = [['coordinator'], ['c@example.com', 'c@example.com']]
        module = load('fieldpulse/coordinator_notifications.py', frappe,
            types.SimpleNamespace(get_url_to_form=lambda *args: 'https://example.com/app/scout-application/APP'))
        module.application_received(Row(name='APP', full_name='<script>', county='A&B'))
        mail = frappe.sendmail.call_args.kwargs
        self.assertEqual(mail['recipients'], ['c@example.com'])
        self.assertTrue(mail['delayed'])
        self.assertIn('&lt;script&gt;', mail['message'])
        self.assertIn('A&amp;B', mail['message'])
        self.assertIn('https://example.com/app/scout-application/APP', mail['message'])
        self.assertIn('DD_logo.png', mail['message'])
        self.assertIn('bgcolor="#07786f"', mail['message'])
        self.assertIn('Review application', mail['message'])
        self.assertNotIn('Reset password', mail['message'])
        self.assertEqual(mail['reference_name'], 'APP')

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
