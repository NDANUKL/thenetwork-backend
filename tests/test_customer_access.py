"""Client activation cannot bypass beta approval or email verification."""
import types
import unittest
from unittest.mock import MagicMock, patch

from test_native_integration import fake_frappe, load


class Record(dict):
    def __getattr__(self, name):
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value


def record(**values):
    doc = Record(values)
    doc.save = MagicMock()
    doc.is_new = lambda: False
    doc.get_doc_before_save = lambda: Record(values)
    doc.set = lambda key, value: doc.__setitem__(key, value)
    return doc


class CustomerAccessTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_frappe()
        self.f.session.user = 'manager@example.test'
        self.f.get_roles.return_value = ['System Manager']
        self.f.flags = types.SimpleNamespace(dd_customer_access_write=False)
        self.f.db.get_value.return_value = None
        self.api = load('customer_access_test', 'fieldpulse/customer_access.py', {
            'frappe': self.f, 'frappe.utils': types.SimpleNamespace(now_datetime=lambda: 'now'),
        })
        self.profile = record(name='CLIENT-1', user='client@example.test', account_access='Active',
                              beta_access='Approved', email_verified=1, approval_email_id='approval-original')
        self.user = record(name='client@example.test', user_type='Website User', enabled=1,
                           roles=[types.SimpleNamespace(role='DD Customer')], api_key='key', api_secret='secret')
        self.f.get_doc.side_effect = [self.profile, self.user]

    def test_only_system_managers_can_change_client_activation(self):
        for roles in ([], ['DD Customer'], ['Field Agent'], ['Field Operations Coordinator'], ['Admin']):
            self.f.get_roles.return_value = roles
            for action in ('Deactivate', 'Reactivate'):
                with self.subTest(roles=roles, action=action), self.assertRaises(PermissionError):
                    self.api.set_account_access('CLIENT-1', action, 'Reason')
        self.f.get_doc.assert_not_called()

    def test_deactivation_retains_approval_and_data_and_revokes_credentials(self):
        clear = MagicMock()
        with patch.dict('sys.modules', {'frappe.sessions': types.SimpleNamespace(clear_sessions=clear)}):
            result = self.api.set_account_access('CLIENT-1', 'Deactivate', 'Requested by client')
        self.assertEqual(result, {'status': 'Deactivated'})
        self.assertEqual(self.user.enabled, 0)
        self.assertIsNone(self.user.api_key)
        self.assertIsNone(self.user.api_secret)
        self.assertIsNone(self.user.reset_password_key)
        self.assertEqual(self.profile.beta_access, 'Approved')
        self.assertEqual(self.profile.approval_email_id, 'approval-original')
        self.assertEqual(self.profile.deactivated_by, 'manager@example.test')
        self.assertEqual(self.profile.deactivation_reason, 'Requested by client')
        clear.assert_not_called()
        self.f.db.after_commit.add.call_args.args[0]()
        clear.assert_called_once_with(user='client@example.test', force=True)
        self.f.delete_doc.assert_not_called()
        self.f.db.commit.assert_not_called()

    def test_reactivation_preserves_each_approval_decision(self):
        for approval in ('Pending', 'Rejected', 'Approved', ''):
            self.profile.account_access = 'Deactivated'
            self.profile.beta_access = approval
            self.profile.deactivation_reason = 'Original reason'
            self.user.enabled, self.user.api_key, self.user.api_secret = 0, None, None
            self.f.get_doc.side_effect = [self.profile, self.user]
            result = self.api.set_account_access('CLIENT-1', 'Reactivate', 'Returned')
            self.assertEqual(result, {'status': 'Active'})
            self.assertEqual(self.user.enabled, 1)
            self.assertEqual(self.profile.beta_access, approval)
            self.assertEqual(self.profile.deactivation_reason, 'Original reason')
            self.assertEqual(self.profile.reactivation_reason, 'Returned')
            self.assertIsNone(self.user.api_key)
            self.assertIsNone(self.user.api_secret)
        self.f.db.after_commit.add.assert_not_called()

    def test_reactivation_does_not_skip_email_verification(self):
        self.profile.account_access, self.profile.email_verified = 'Deactivated', 0
        self.api.set_account_access('CLIENT-1', 'Reactivate', 'Return')
        self.assertEqual(self.user.enabled, 0)
        self.assertEqual(self.profile.email_verified, 0)

    def test_deactivated_accounts_are_blocked_on_login_requests_and_direct_user_enable(self):
        self.f.db.get_value.return_value = 'Deactivated'
        actions = [lambda: self.api.on_login(types.SimpleNamespace(user=self.profile.user)),
                   self.api.validate_auth, lambda: self.api.validate_user(self.user)]
        for action in actions:
            with self.assertRaises(PermissionError): action()

    def test_ordinary_document_edits_cannot_restore_activation_or_change_identity(self):
        self.profile.account_access = 'Deactivated'
        with self.assertRaises(ValueError): self.api.validate_account(self.profile)
        self.profile.account_access = 'Active'
        self.profile.user = 'someone-else@example.test'
        with self.assertRaises(ValueError): self.api.validate_account(self.profile)

    def test_approved_clients_cannot_be_rejected_or_returned_to_pending(self):
        for original in ('Approved', None, ''):
            for target in ('Rejected', 'Pending'):
                self.profile.get_doc_before_save = lambda: Record(user=self.profile.user, beta_access=original)
                self.profile.beta_access = target
                with self.subTest(original=original, target=target), self.assertRaisesRegex(ValueError, 'Use Deactivate'):
                    self.api.validate_account(self.profile)

    def test_pending_approval_and_rejection_and_reconsidering_rejection_remain_allowed(self):
        for original, target in [('Pending', 'Approved'), ('Pending', 'Rejected'), ('Rejected', 'Approved')]:
            previous = Record(user=self.profile.user, beta_access=original, account_access='Active')
            self.profile.get_doc_before_save = lambda: previous
            self.profile.beta_access = target
            self.api.validate_account(self.profile)

    def test_deactivated_accounts_cannot_change_approval_until_reactivated(self):
        self.profile.account_access, self.profile.beta_access = 'Deactivated', 'Approved'
        self.profile.get_doc_before_save = lambda: Record(user=self.profile.user, account_access='Deactivated', beta_access='Pending')
        with self.assertRaisesRegex(ValueError, 'Reactivate'):
            self.api.validate_account(self.profile)

    def test_pending_and_rejected_clients_cannot_be_deactivated_even_in_public_mode(self):
        self.f.db.get_single_value.return_value = 'Open to everyone'
        for approval in ('Pending', 'Rejected'):
            self.profile.beta_access = approval
            self.f.get_doc.side_effect = [self.profile, self.user]
            with self.subTest(approval=approval), self.assertRaisesRegex(ValueError, 'Only approved'):
                self.api.set_account_access('CLIENT-1', 'Deactivate', 'Reason')
        self.profile.save.assert_not_called()
        self.user.save.assert_not_called()

    def test_staff_and_self_accounts_cannot_be_changed_by_client_action(self):
        for value in ('System User',):
            self.user.user_type = value
            with self.assertRaises(ValueError): self.api.set_account_access('CLIENT-1', 'Deactivate', 'Reason')
        self.user.user_type = 'Website User'
        self.f.get_doc.side_effect = [self.profile, self.user]
        self.f.db.get_value.return_value = 1
        with self.assertRaises(ValueError): self.api.set_account_access('CLIENT-1', 'Deactivate', 'Reason')
        self.profile.save.assert_not_called()

    def test_invalid_actions_missing_reasons_and_stale_reactivation_fail(self):
        for action, reason in [('Approved', 'Reason'), ('Deactivate', ''), ('Reactivate', ' ')]:
            with self.assertRaises(ValueError): self.api.set_account_access('CLIENT-1', action, reason)
        self.f.get_doc.assert_not_called()
        with self.assertRaises(ValueError): self.api.set_account_access('CLIENT-1', 'Reactivate', 'Reason')
        self.profile.save.assert_not_called()

    def test_failed_user_save_leaves_transaction_and_resets_internal_flag(self):
        self.user.save.side_effect = RuntimeError('write failed')
        with self.assertRaises(RuntimeError): self.api.set_account_access('CLIENT-1', 'Deactivate', 'Reason')
        self.assertFalse(self.f.flags.dd_customer_access_write)
        self.f.db.commit.assert_not_called()
        self.f.db.after_commit.add.assert_not_called()

    def test_repeat_signup_recovery_and_verification_cannot_reactivate_client(self):
        self.profile.account_access = 'Deactivated'
        self.f.db.exists.side_effect = lambda dt, *args: 'CLIENT-1' if dt == 'DD Customer Account' else True
        self.f.get_doc.side_effect = lambda dt, *args, **kwargs: self.profile if dt == 'DD Customer Account' else self.user
        ownership = types.SimpleNamespace(owned_event=lambda *args: lambda f: f, owned_api=lambda *args: lambda f: f)
        bridge = load('customer_access_bridge_test', 'fieldpulse/customer_accounts.py', {
            'frappe': self.f, 'fieldpulse.native_ownership': ownership,
            'fieldpulse.beta_access': types.SimpleNamespace(registration_access=lambda: 'Open to everyone', access_status=MagicMock()),
        })
        for action in ('register', 'recover', 'verify', 'profile'):
            self.f.form_dict = {'action': action, 'email': self.profile.user}
            if action in ('register', 'recover'):
                self.assertEqual(bridge.registration(), {'eligible': False})
            else:
                with self.assertRaises(PermissionError): bridge.registration()
        self.profile.save.assert_not_called()
        self.user.save.assert_not_called()


if __name__ == '__main__':
    unittest.main()
