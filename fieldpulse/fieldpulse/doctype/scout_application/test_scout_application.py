"""Run on staging: bench --site <site> run-tests --doctype 'Scout Application'."""
from uuid import uuid4

import frappe
from frappe.tests.utils import FrappeTestCase

from fieldpulse.auth import register_field_agent, mobile_login
from fieldpulse.scout_access import check_access, review_application, deactivate_scout


class TestScoutApplication(FrappeTestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user("Administrator")
        self.addCleanup(frappe.set_user, self.previous_user)
        self.email = f"scout-{uuid4().hex}@example.test"
        self.password = f"Scout!{uuid4().hex}"

    def apply(self):
        result = register_field_agent("Approval Test", self.email, self.password,
                                      phone="0712345678", county="Kiambu")
        self.assertEqual(result["status"], "Pending")
        self.assertNotIn("sid", result)
        self.assertFalse(frappe.db.get_value("User", self.email, "enabled"))
        self.assertFalse(frappe.db.exists("Scout Profile", {"user": self.email}))
        self.assertFalse(frappe.db.exists("FP Agent", {"user": self.email}))
        self.assertNotIn("Field Agent", frappe.get_roles(self.email))
        return frappe.db.get_value("Scout Application", {"email": self.email}, "name")

    def test_pending_approval_and_deactivation(self):
        application = self.apply()
        with self.assertRaises(frappe.PermissionError):
            mobile_login(self.email, self.password)
        result = review_application(application, "Approved")
        self.assertTrue(frappe.db.get_value("User", self.email, "enabled"))
        self.assertIn("Field Agent", frappe.get_roles(self.email))
        self.assertEqual(frappe.db.count("Scout Profile", {"user": self.email}), 1)
        profile = frappe.get_doc("Scout Profile", result["scout_profile"])
        self.assertEqual(profile.base_county, "Kiambu")
        check_access(self.email)
        deactivate_scout(profile.name, "Left the team")
        self.assertFalse(frappe.db.get_value("User", self.email, "enabled"))
        self.assertEqual(frappe.db.get_value("FP Agent", {"user": self.email}, "status"), "Suspended")
        with self.assertRaises(frappe.PermissionError): check_access(self.email)
        with self.assertRaises(frappe.ValidationError):
            register_field_agent("Approval Test", self.email, self.password, county="Kiambu")
        # Saving User directly must not reverse the access decision.
        user = frappe.get_doc("User", self.email)
        user.enabled = 1
        with self.assertRaises(frappe.ValidationError): user.save(ignore_permissions=True)

    def test_rejected_application_never_gets_a_profile(self):
        application = self.apply()
        review_application(application, "Rejected", "Not eligible")
        self.assertFalse(frappe.db.exists("Scout Profile", {"user": self.email}))
        self.assertFalse(frappe.db.get_value("User", self.email, "enabled"))
        with self.assertRaises(frappe.PermissionError): check_access(self.email)
        with self.assertRaises(frappe.ValidationError): review_application(application, "Approved")

    def test_ordinary_user_cannot_review_applications(self):
        application = self.apply()
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError): review_application(application, "Approved")
