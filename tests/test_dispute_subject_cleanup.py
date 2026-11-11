"""Subject-free disputes keep ownership, retry identity and historical values."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).parents[1]

class DisputeSubjectTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.whitelist = lambda **kwargs: lambda fn: fn
        def fail(message):
            raise ValueError(message)
        self.f.throw.side_effect = fail
        self.f.db.get_value.return_value = None
        self.f.get_doc.return_value.name = 'DIS-1'
        self.owned = MagicMock(return_value=MagicMock(name='request'))
        self.lock = MagicMock()
        source = ast.parse((ROOT / 'fieldpulse/commerce.py').read_text(encoding='utf-8'))
        selected = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in ('create_dispute', 'disputes', 'validate_dispute')]
        self.env = dict(frappe=self.f, ddowned=self.owned, ddlock=self.lock, ddcustomer=lambda: 'ACCOUNT-1', now_datetime=lambda: '2026-11-11')
        exec(compile(ast.Module(body=selected, type_ignores=[]), 'commerce.py', 'exec'), self.env)

    def test_create_without_subject(self):
        result = self.env['create_dispute']('DD-1', '  Please review the missing photographs.  ', 'retry-1')
        self.assertTrue(result['success'])
        self.owned.assert_called_once_with('DD-1')
        self.lock.assert_called_once()
        payload = self.f.get_doc.call_args.args[0]
        self.assertNotIn('subject', payload)
        self.assertEqual(payload['reason'], 'Please review the missing photographs.')
        self.assertEqual(payload['customer_account'], 'ACCOUNT-1')
        self.f.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

    def test_duplicate_does_not_insert(self):
        self.f.db.get_value.return_value = 'DIS-EXISTING'
        result = self.env['create_dispute']('DD-1', 'Please review the missing photographs.', 'retry-1')
        self.assertEqual(result['dispute']['name'], 'DIS-EXISTING')
        self.f.get_doc.assert_not_called()

    def test_validation_and_ownership_still_apply(self):
        for reason in (None, 'short', ' ' * 30, 'x' * 4001):
            with self.assertRaises(ValueError):
                self.env['create_dispute']('DD-1', reason, 'retry-1')
        with self.assertRaises(ValueError):
            self.env['create_dispute']('DD-1', 'Please review the missing photographs.', '')
        self.owned.side_effect = PermissionError('Not yours')
        with self.assertRaises(PermissionError):
            self.env['create_dispute']('OTHER', 'Please review the missing photographs.', 'retry-1')
        self.f.get_doc.assert_not_called()

    def test_list_no_longer_selects_subject(self):
        self.env['disputes']()
        args = self.f.get_all.call_args.kwargs
        self.assertNotIn('subject', args['fields'])
        self.assertEqual(args['filters'], {'customer_account': 'ACCOUNT-1'})

    def test_historical_subject_is_retained_hidden_optional_and_protected(self):
        schema = json.loads((ROOT / 'fieldpulse/fieldpulse/doctype/dd_dispute/dd_dispute.json').read_text(encoding='utf-8'))
        field = next(row for row in schema['fields'] if row['fieldname'] == 'subject')
        self.assertEqual((field['hidden'], field['reqd'], field['read_only']), (1, 0, 1))
        doc = MagicMock()
        doc.request = 'DD-1'
        doc.customer_account = 'ACCOUNT-1'
        self.f.get_doc.return_value.dd_customer_account = 'ACCOUNT-1'
        previous = MagicMock()
        previous.get.side_effect = lambda key: 'Old subject' if key == 'subject' else 'unchanged'
        doc.get.side_effect = lambda key: 'Replaced subject' if key == 'subject' else 'unchanged'
        doc.get_doc_before_save.return_value = previous
        with self.assertRaisesRegex(ValueError, 'Original dispute details'):
            self.env['validate_dispute'](doc)

if __name__ == '__main__':
    unittest.main()
