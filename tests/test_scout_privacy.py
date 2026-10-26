import importlib.util
from pathlib import Path
import re
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class ScoutPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.whitelist = lambda **kwargs: lambda fn: fn
        self.f.session.user = 'scout@example.test'
        self.f.conf = {'host_name': 'https://service.example.test'}
        self.f.flags.scout_data_request = None
        self.f.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(PermissionError(message))
        limiter = types.ModuleType('frappe.rate_limiter')
        limiter.rate_limit = lambda **kwargs: lambda fn: fn
        utils = types.ModuleType('frappe.utils')
        utils.get_url = lambda: 'https://service.example.test'
        utils.validate_email_address = lambda value, **kwargs: value
        password = types.ModuleType('frappe.utils.password')
        self.check_password = password.check_password = MagicMock()
        spec = importlib.util.spec_from_file_location('scout_privacy_test', Path(__file__).parents[1] / 'fieldpulse/scout_privacy.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.f, 'frappe.rate_limiter': limiter, 'frappe.utils': utils, 'frappe.utils.password': password}):
            spec.loader.exec_module(self.module)
        self.module._is_scout = lambda user: user == 'scout@example.test'

    def test_guest_cannot_submit_a_signed_in_request(self):
        self.f.session.user = 'Guest'
        with self.assertRaises(PermissionError): self.module.request_deletion('password')
        self.check_password.assert_not_called()

    def test_password_is_checked_for_the_session_owner(self):
        self.module._request = MagicMock(return_value={'reference': 'reference'})
        self.check_password.side_effect = PermissionError('Invalid password')
        with self.assertRaises(PermissionError): self.module.request_deletion('wrong', 'reason')
        self.module._request.assert_not_called()
        self.check_password.side_effect = None
        self.module.request_deletion('correct', 'reason')
        self.check_password.assert_called_with('scout@example.test', 'correct')
        self.module._request.assert_called_once_with('scout@example.test', 'reason')

    def test_public_email_response_does_not_disclose_membership(self):
        unknown = self.module.email_deletion_link('unknown@example.test')
        self.f.sendmail.assert_not_called()
        known = self.module.email_deletion_link('scout@example.test', 'reason')
        self.assertEqual(unknown, known)
        key, payload = self.f.cache().set_value.call_args.args
        self.assertNotIn('scout@example.test', key)
        self.assertEqual(payload['user'], 'scout@example.test')
        self.assertEqual(self.f.cache().set_value.call_args.kwargs['expires_in_sec'], 1800)
        message = self.f.sendmail.call_args.kwargs['message']
        self.assertIn('/scout-data-deletion#token=', message)
        self.assertNotIn('?token=', message)

    def test_expired_email_link_cannot_create_a_request(self):
        self.f.cache().get_value.return_value = None
        self.module._request = MagicMock()
        with self.assertRaises(PermissionError): self.module.confirm_email_deletion('x' * 43)
        self.module._request.assert_not_called()

    def test_confirm_uses_verified_identity_and_consumes_token_after_commit(self):
        self.f.cache().get_value.return_value = {'user': 'scout@example.test', 'reason': 'Verified reason'}
        self.module._request = MagicMock(return_value={'reference': 'request', 'status': 'Open'})
        result = self.module.confirm_email_deletion('x' * 43)
        self.assertEqual(result['reference'], 'request')
        self.module._request.assert_called_once_with('scout@example.test', 'Verified reason')
        self.f.db.commit.assert_called_once()
        self.f.cache().delete_value.assert_called_once()

    def test_duplicate_request_reuses_open_reference(self):
        self.f.db.get_value.return_value = 'existing'
        doc = types.SimpleNamespace(name='existing', status='Open', creation='now', get=lambda key: '')
        self.f.get_doc.return_value = doc
        self.assertEqual(self.module._request('scout@example.test', 'Reason')['reference'], 'existing')
        self.f.db.sql.assert_called_once()
        self.f.get_doc.assert_called_once_with('Scout Data Request', 'existing')

    def test_status_is_scoped_to_owner(self):
        self.f.get_all.return_value = []
        self.assertEqual(self.module.deletion_status(), {'request': None})
        self.assertEqual(self.f.get_all.call_args.kwargs['filters'], {'user': 'scout@example.test'})

    def test_email_confirmation_origin_cannot_come_from_the_request_host(self):
        self.f.conf = {}
        with self.assertRaises(PermissionError): self.module.email_deletion_link('scout@example.test')
        self.f.sendmail.assert_not_called()
