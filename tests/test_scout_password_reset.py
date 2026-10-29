import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).parents[1]

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock()
        self.f.whitelist.return_value=lambda fn:fn
        self.f.throw.side_effect=ValueError
        self.f.session.user='Guest'
        self.native=MagicMock(MAX_PASSWORD_SIZE=1000)
        self.native._get_user_for_update_password.return_value={'user':'scout@example.test'}
        self.native.test_password_strength.return_value={}
        self.store=MagicMock()
        modules={'frappe':self.f,'frappe.rate_limiter':types.SimpleNamespace(rate_limit=lambda **kwargs:lambda fn:fn),
          'frappe.utils':types.SimpleNamespace(today=lambda:'2026-10-29'),
          'frappe.utils.password':types.SimpleNamespace(update_password=self.store),
          'frappe.core.doctype.user':types.SimpleNamespace(user=self.native)}
        self.patcher=patch.dict(sys.modules,modules);self.patcher.start();self.addCleanup(self.patcher.stop)
        spec=importlib.util.spec_from_file_location('reset_test',ROOT/'fieldpulse/scout_password_reset.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def reset(self):return self.module.update_password('New-password-123',key='valid-key')

    def test_scout_resets_without_browser_login_or_desk_redirect(self):
        self.assertEqual(self.reset(),'/scout-password-reset-complete')
        self.store.assert_called_once_with('scout@example.test','New-password-123',logout_all_sessions=1)
        self.f.local.login_manager.login_as.assert_not_called()
        self.native.update_password.assert_not_called()
        changes=self.f.db.set_value.call_args.args[2]
        self.assertEqual(changes['reset_password_key'],'');self.assertEqual(changes['redirect_url'],'')

    def test_invalid_expired_and_concurrently_used_tokens_do_not_change_password(self):
        for responses in ([{'message':'Expired'}],[{'user':'scout@example.test'},{'message':'Used'}]):
            self.native._get_user_for_update_password.side_effect=responses
            self.reset();self.assertEqual(self.f.local.response.http_status_code,410)
        self.store.assert_not_called();self.f.local.login_manager.login_as.assert_not_called()

    def test_non_scout_recovery_and_non_token_changes_keep_framework_behavior(self):
        self.f.db.exists.return_value=False
        self.reset();self.native.update_password.assert_called_once()
        self.native.update_password.reset_mock()
        self.module.update_password('New-password-123',old_password='old')
        self.native.update_password.assert_called_once();self.store.assert_not_called()

    def test_weak_password_is_rejected_before_consuming_token(self):
        self.native.test_password_strength.return_value={'feedback':{'password_policy_validation_passed':False}}
        self.native.handle_password_test_fail.side_effect=ValueError('weak')
        with self.assertRaises(ValueError):self.reset()
        self.store.assert_not_called();self.f.db.set_value.assert_not_called()

    def test_existing_scout_browser_session_is_logged_out(self):
        self.f.session.user='scout@example.test'
        self.reset();self.f.local.login_manager.logout.assert_called_once()
        self.f.local.login_manager.login_as.assert_not_called()
