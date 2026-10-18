"""Mobile identity validation and profile mapping regressions."""
import types
import unittest
from unittest.mock import MagicMock, patch
from test_native_integration import fake_frappe, load


class ScoutRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.frappe = fake_frappe()
        self.utils = types.ModuleType("frappe.utils")
        self.utils.get_url = lambda: "https://example.test"
        self.utils.validate_email_address = lambda email, **kwargs: email
        self.utils.now_datetime = lambda: "2026-10-18 12:00:00"
        self.auth = load("scout_auth_test", "fieldpulse/auth.py", {
            "frappe": self.frappe, "frappe.utils": self.utils,
        })

    def test_single_name_and_missing_county_rejected_before_writes(self):
        for name, county in [("Pauline", "Nairobi"), ("Pauline 123", "Nairobi"),
                             ("Pauline Wanjiku", ""), ("Pauline Wanjiku", None)]:
            with self.subTest(name=name, county=county), self.assertRaises(ValueError):
                self.auth.register_field_agent(name, "scout@example.test", "password123", county=county)
        self.frappe.get_doc.assert_not_called()

    def test_registration_updates_existing_profile_without_resetting_leave(self):
        user = MagicMock(name="user")
        user.name = "scout@example.test"
        agent = MagicMock(name="agent")
        agent.name = "AGT-123"
        profile = MagicMock(name="profile")
        profile.availability_status = "On Leave"
        self.frappe.db.exists.side_effect = [False, "SCT-00001"]
        self.frappe.get_doc.side_effect = [user, agent, profile]
        with patch.object(self.auth, "_login", return_value={"sid": "test"}):
            self.auth.register_field_agent(" Pauline   Wanjiku ", "scout@example.test", "password123",
                                           phone="0712345678", county=" Nairobi ")
        self.assertEqual(profile.scout_name, "Pauline Wanjiku")
        self.assertEqual(profile.base_county, "Nairobi")
        self.assertEqual(profile.legacy_fp_agent, "AGT-123")
        self.assertEqual(profile.availability_status, "On Leave")
        profile.save.assert_called_once_with(ignore_permissions=True)

    def test_login_records_activity_after_authentication(self):
        self.frappe.db.exists.return_value = "SCT-00001"
        with patch.dict("sys.modules", {"frappe.utils": self.utils}):
            self.auth._login("scout@example.test", "password123")
        self.frappe.auth.LoginManager.return_value.authenticate.assert_called_once()
        self.frappe.db.set_value.assert_called_once_with("Scout Profile", "SCT-00001", {
            "last_app_activity": "2026-10-18 12:00:00", "activity_status": "Active",
        }, update_modified=False)
