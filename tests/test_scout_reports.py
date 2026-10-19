import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


class Record(dict):
    def __getattr__(self, key): return self.get(key)


class ReportSecurityTests(unittest.TestCase):
    def setUp(self):
        self.api = MagicMock()
        self.api.whitelist = lambda **kw: lambda fn: fn
        self.api.PermissionError = PermissionError
        self.api.response = {}
        def reject(message, error=ValueError): raise error(message)
        self.api.throw.side_effect = reject
        self.owned = MagicMock()
        payments = types.ModuleType('fieldpulse.payments')
        payments._customer = MagicMock()
        payments._owned = self.owned
        payments._lock = MagicMock()
        utils = types.ModuleType('frappe.utils')
        utils.now_datetime = lambda: '2026-10-20 09:00:00'
        spec = importlib.util.spec_from_file_location('report_commerce_test', ROOT / 'fieldpulse/commerce.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe':self.api, 'frappe.utils':utils, 'fieldpulse.payments':payments}): spec.loader.exec_module(self.module)

    def test_approved_pdf_can_be_downloaded_before_any_balance_payment(self):
        self.api.db.get_value.side_effect = lambda dt, *a, **kw: 'report' if dt == 'DD Service Report' else 'file' if dt == 'File' else None
        report = Record(name='report', title='Plot report', approved_at='today', report_file='/private/files/report.pdf')
        file = Record(file_name='report.pdf', get_content=lambda:b'%PDF-1.7\ncomplete approved report')
        self.api.get_doc.side_effect = [report, report, file]
        bundle = types.ModuleType('fieldpulse.scout_reports')
        bundle.build_report_bundle = MagicMock(return_value=b'PK-test-bundle')
        with patch.dict(sys.modules, {'fieldpulse.scout_reports': bundle}):
            self.module.download_report('request')
        bundle.build_report_bundle.assert_called_once_with(report, b'%PDF-1.7\ncomplete approved report')
        self.owned.assert_called_with('request')
        self.assertEqual(self.api.response['filecontent'], b'PK-test-bundle')
        self.assertEqual(self.api.response['content_type'], 'application/zip')
        self.assertFalse(any(call.args[0]=='DD Payment' for call in self.api.db.get_value.call_args_list))

    def test_foreign_request_is_rejected_before_report_lookup(self):
        self.owned.side_effect = PermissionError('Not owned')
        with self.assertRaises(PermissionError): self.module.report('foreign-request')
        self.api.db.get_value.assert_not_called()

    def test_unapproved_report_is_not_exposed(self):
        self.api.db.get_value.return_value = None
        self.assertEqual(self.module.report('request'), {'report':None})

    def test_file_must_be_attached_to_the_report_being_approved(self):
        self.api.get_roles.return_value = ['Field Operations Coordinator']
        self.api.db.exists.return_value = True
        self.api.get_doc.return_value = Record(attached_to_doctype='DD Service Report', attached_to_name='another-report')
        report = Record(name='report', request='request', status='Approved', report_file='/private/files/test.pdf', get_doc_before_save=lambda:None)
        with self.assertRaisesRegex(ValueError, 'own Service Report'): self.module.validate_report(report)


if __name__ == '__main__': unittest.main()
