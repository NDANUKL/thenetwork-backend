"""Staging: bench --site <site> run-tests --doctype 'DD Customer Account'."""
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from fieldpulse.customer_access import set_account_access, check_access, access_write
from fieldpulse.beta_access import access_status


class TestDDCustomerAccount(FrappeTestCase):
    def setUp(self):
        previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, previous_user)

    def account(self, approval="Approved", verified=1):
        email = f"activation-{uuid4().hex}@example.test"
        frappe.get_doc({"doctype": "User", "email": email, "first_name": "Activation Test",
                        "enabled": verified, "user_type": "Website User", "send_welcome_email": 0,
                        "roles": [{"role": "DD Customer"}]}).insert(ignore_permissions=True)
        return frappe.get_doc({"doctype": "DD Customer Account", "user": email,
                               "beta_access": approval, "email_verified": verified}).insert(ignore_permissions=True)

    def test_deactivate_reactivate_retains_account_and_approval(self):
        account = self.account()
        set_account_access(account.name, "Deactivate", "Client paused account")
        account.reload()
        self.assertEqual(account.beta_access, "Approved")
        self.assertEqual(access_status(account), "Deactivated")
        self.assertFalse(frappe.db.get_value("User", account.user, "enabled"))
        with self.assertRaises(frappe.PermissionError): check_access(account.user)
        set_account_access(account.name, "Reactivate", "Client returned")
        account.reload()
        check_access(account.user)
        self.assertEqual(account.beta_access, "Approved")
        self.assertEqual(account.deactivation_reason, "Client paused account")
        self.assertEqual(account.reactivation_reason, "Client returned")
        self.assertTrue(frappe.db.get_value("User", account.user, "enabled"))
        self.assertEqual(frappe.db.count("DD Customer Account", {"user": account.user}), 1)

    def test_reactivation_preserves_rejection_and_email_verification(self):
        for approval, verified in [("Rejected", 1), ("Pending", 0)]:
            account = self.account(approval, verified)
            # Historical accounts may have been deactivated before the approval-only guard.
            with access_write():
                account.account_access = "Deactivated"
                account.save(ignore_permissions=True)
            frappe.db.set_value("User", account.user, "enabled", 0)
            set_account_access(account.name, "Reactivate", "Returned")
            account.reload()
            self.assertEqual(account.beta_access, approval)
            self.assertEqual(account.email_verified, verified)
            self.assertEqual(frappe.db.get_value("User", account.user, "enabled"), verified)
            if approval == "Rejected": self.assertEqual(access_status(account), "Rejected")

    def test_approved_client_cannot_be_rejected_and_pending_cannot_be_deactivated(self):
        account = self.account()
        account.beta_access = "Rejected"
        with self.assertRaises(frappe.ValidationError): account.save(ignore_permissions=True)
        pending = self.account("Pending")
        with self.assertRaises(frappe.ValidationError):
            set_account_access(pending.name, "Deactivate", "Reason")

    def test_client_cannot_manage_its_own_activation(self):
        account = self.account()
        frappe.set_user(account.user)
        with self.assertRaises(frappe.PermissionError):
            set_account_access(account.name, "Deactivate", "Attempt")
