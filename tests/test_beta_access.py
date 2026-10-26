import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]

def load(relative, api, extra=None):
    spec = importlib.util.spec_from_file_location("test_target", ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"frappe": api, "requests": MagicMock(), **(extra or {})}):
        spec.loader.exec_module(module)
    return module

class AccessTests(unittest.TestCase):
    def setUp(self):
        self.api = MagicMock()
        self.api.whitelist = lambda **kwargs: lambda f: f
        self.api.PermissionError = PermissionError
        self.api.throw.side_effect = lambda message, error=ValueError: (_ for _ in ()).throw(error(message))
        self.api.db.get_single_value.return_value = "Invite only"
        self.policy = load("fieldpulse/beta_access.py", self.api)

    def test_existing_accounts_remain_approved(self):
        for status in (None, "", "Approved"):
            self.assertEqual(self.policy.access_status({"beta_access": status}), "Approved")

    def test_public_switch_admits_pending_but_preserves_rejection(self):
        self.assertEqual(self.policy.access_status({"beta_access": "Pending"}), "Pending")
        self.api.db.get_single_value.return_value = "Open to everyone"
        self.assertEqual(self.policy.access_status({"beta_access": "Pending"}), "Approved")
        self.assertEqual(self.policy.access_status({"beta_access": "Rejected"}), "Rejected")

    def test_backend_gate_blocks_pending_rejected_and_unknown(self):
        for status in ("Pending", "Rejected", "unexpected"):
            with self.assertRaises(PermissionError):
                self.policy.require_access({"beta_access": status})
        self.policy.require_access({})

    def test_deactivation_overrides_public_registration_without_changing_approval(self):
        self.api.db.get_single_value.return_value = "Open to everyone"
        for approval in ('Approved', 'Pending', 'Rejected', ''):
            account = {'beta_access': approval, 'account_access': 'Deactivated'}
            self.assertEqual(self.policy.access_status(account), 'Deactivated')
            with self.assertRaises(PermissionError): self.policy.require_access(account)
            self.assertEqual(account['beta_access'], approval)

    def test_reactivation_restores_original_approval_policy(self):
        for approval in ('Pending', 'Rejected', 'Approved'):
            account = {'beta_access': approval, 'account_access': 'Active'}
            self.assertEqual(self.policy.access_status(account), approval)

    def test_approval_mail_is_not_sent_to_rejected_pending_unverified_or_notified(self):
        notifications = load("fieldpulse/access_notifications.py", self.api)
        for status, verified, sent in [("Pending",1,None),("Rejected",1,None),("Approved",0,None),("Approved",1,"today")]:
            account = MagicMock()
            data = dict(beta_access=status, approval_email_id="id", approval_email_sent_at=sent)
            account.get.side_effect = data.get
            account.email_verified = verified
            self.api.get_doc.return_value = account
            with patch.object(notifications.requests, "post") as post:
                notifications.send_approval("account")
                post.assert_not_called()

    def test_approval_email_is_not_sent_to_deactivated_account(self):
        notifications = load('fieldpulse/access_notifications.py', self.api)
        account = MagicMock()
        account.get.side_effect = dict(beta_access='Approved', account_access='Deactivated', approval_email_id='id').get
        account.email_verified = 1
        self.api.get_doc.return_value = account
        with patch.object(notifications.requests, 'post') as post:
            notifications.send_approval('account')
            post.assert_not_called()

    def test_approval_mail_uses_stable_key_and_records_success_only(self):
        notifications = load("fieldpulse/access_notifications.py", self.api)
        account = MagicMock()
        account.get.side_effect = dict(beta_access="Approved", approval_email_id="abc", approval_email_sent_at=None).get
        account.approval_email_id = "abc"
        account.email_verified = 1
        account.user = "test@example.com"
        settings = MagicMock(customer_origin="https://diaspora-desk.com", resend_from_email="Diaspora Desk <no-reply@diaspora-desk.com>")
        settings.get_password.return_value = "test-secret"
        self.api.get_doc.side_effect = [account, settings]
        with patch.object(notifications.requests, "post", return_value=MagicMock(ok=True)) as post:
            notifications.send_approval("account")
            self.assertEqual(post.call_args.kwargs["headers"]["Idempotency-Key"], "dd-access-abc")
            self.assertIn("images/DD_logo.png", post.call_args.kwargs["json"]["html"])
            account.db_set.assert_called_once()

if __name__ == "__main__":
    unittest.main()
