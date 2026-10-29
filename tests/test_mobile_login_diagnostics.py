"""Login diagnostics must retain denials, exception identity and private data boundaries."""
import types
import unittest
from unittest.mock import Mock, patch
from test_scout_registration import ScoutRegistrationTests
from test_native_integration import load


class MobileLoginDiagnosticsTests(unittest.TestCase):
    setUp = ScoutRegistrationTests.setUp

    def test_real_admission_denials_keep_permissions_and_emit_codes(self):
        access = load('diagnostic_access_test', 'fieldpulse/scout_access.py', {
            'frappe': self.frappe, 'frappe.utils': self.utils})
        cases = [('Pending', None, True, 'SCOUT_APPROVAL_PENDING'),
                 ('Rejected', None, True, 'SCOUT_APPLICATION_REJECTED'),
                 ('Deactivated', None, True, 'SCOUT_ACCESS_DEACTIVATED'),
                 ('Approved', 'Deactivated', True, 'SCOUT_ACCESS_DEACTIVATED'),
                 ('Approved', 'Active', False, 'LOGIN_ACCOUNT_DISABLED')]
        for status, profile, enabled, code in cases:
            self.frappe.response.clear()
            self.frappe.db.get_value.side_effect = lambda dt, *a: {'Scout Application': status, 'Scout Profile': profile, 'User': enabled}[dt]
            with patch.dict('sys.modules', {'fieldpulse.scout_access': access}), patch.object(self.auth, '_login') as login:
                with self.assertRaises(PermissionError):
                    self.auth.mobile_login('synthetic@example.test', 'private-password')
                login.assert_not_called()
            self.assertEqual(self.frappe.response['diagnostic_code'], code)
            self.assertEqual(self.frappe.response['auth_stage'], 'admission')
            self.assertRegex(self.frappe.response['server_reference'], r'^AUTH-[a-f0-9]{32}$')
        self.frappe.log_error.assert_not_called()

    def test_missing_profile_and_inactive_agent_still_block_login(self):
        for exists, code, stage in [([False], 'SCOUT_PROFILE_REQUIRED', 'profile'),
                                    ([True, False], 'SCOUT_AGENT_INACTIVE', 'agent')]:
            self.frappe.response.clear()
            self.frappe.db.exists.side_effect = exists
            with patch.dict('sys.modules', {'fieldpulse.scout_access': types.SimpleNamespace(check_access=lambda email: None)}), patch.object(self.auth, '_login') as login:
                with self.assertRaises(ValueError):
                    self.auth.mobile_login('synthetic@example.test', 'private-password')
                login.assert_not_called()
            self.assertEqual(self.frappe.response['diagnostic_code'], code)
            self.assertEqual(self.frappe.response['auth_stage'], stage)

    def test_unexpected_hook_denial_is_logged_safely_without_replacing_exception(self):
        self.frappe.db.exists.return_value = True
        failure = PermissionError('private-password synthetic@example.test')
        with patch.dict('sys.modules', {'fieldpulse.scout_access': types.SimpleNamespace(check_access=lambda email: None)}), patch.object(self.auth, '_login', side_effect=failure):
            with self.assertRaises(PermissionError) as caught:
                self.auth.mobile_login('synthetic@example.test', 'private-password')
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.frappe.response['diagnostic_code'], 'LOGIN_PERMISSION_DENIED')
        self.assertEqual(self.frappe.response['auth_stage'], 'authentication')
        logged = self.frappe.log_error.call_args.kwargs
        self.assertTrue(logged['defer_insert'])
        self.assertIn(self.frappe.response['server_reference'], logged['message'])
        self.assertNotIn('private-password', logged['message'])
        self.assertNotIn('synthetic@', logged['message'])
        self.frappe.db.commit.assert_not_called()

    def test_success_and_mfa_challenge_are_returned_unchanged(self):
        self.frappe.db.exists.return_value = True
        for result in [{'sid': 'synthetic-session'}, {'two_factor_required': True, 'tmp_id': 'synthetic-challenge'}]:
            self.frappe.response.clear()
            with patch.dict('sys.modules', {'fieldpulse.scout_access': types.SimpleNamespace(check_access=lambda email: None)}), patch.object(self.auth, '_login', return_value=result):
                self.assertIs(self.auth.mobile_login('synthetic@example.test', 'private-password'), result)
            self.assertNotIn('diagnostic_code', self.frappe.response)
        self.frappe.log_error.assert_not_called()
