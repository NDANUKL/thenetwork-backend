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

    def test_registration_creates_disabled_applicant_without_profile_or_session(self):
        user = MagicMock(name="user")
        user.name = "scout@example.test"
        application = MagicMock()
        self.frappe.db.exists.return_value = False
        self.frappe.get_doc.side_effect = [user, application]
        from contextlib import nullcontext
        access = types.SimpleNamespace(admission_write=nullcontext)
        with patch.dict('sys.modules', {'fieldpulse.scout_access': access}), patch.object(self.auth, '_login') as login:
            result = self.auth.register_field_agent(" Pauline   Wanjiku ", "scout@example.test", "password123",
                                                    phone="0712345678", county=" Nairobi ")
        self.assertEqual(result['status'], 'Pending')
        self.assertNotIn('sid', result)
        login.assert_not_called()
        values = [call.args[0] for call in self.frappe.get_doc.call_args_list]
        self.assertEqual([v['doctype'] for v in values], ['User', 'Scout Application'])
        self.assertEqual(values[0]['enabled'], 0)
        self.assertEqual(values[0]['roles'], [])
        self.assertEqual(values[1]['full_name'], 'Pauline Wanjiku')
        self.assertEqual(values[1]['county'], 'Nairobi')
        self.assertNotIn('password', values[1])
        self.frappe.db.commit.assert_not_called()

    def test_repeat_signup_never_recreates_an_existing_identity(self):
        for existing in ([True], [False, True]):
            self.frappe.db.exists.side_effect = existing
            with self.assertRaises(ValueError):
                self.auth.register_field_agent('Pauline Wanjiku', 'scout@example.test', 'password123', county='Nairobi')
        self.frappe.get_doc.assert_not_called()

    def test_login_records_activity_after_authentication(self):
        self.frappe.db.exists.return_value = "SCT-00001"
        with patch.dict("sys.modules", {"frappe.utils": self.utils}):
            self.auth._login("scout@example.test", "password123")
        self.frappe.auth.LoginManager.return_value.authenticate.assert_called_once()
        self.frappe.db.set_value.assert_called_once_with("Scout Profile", "SCT-00001", {
            "last_app_activity": "2026-10-18 12:00:00", "activity_status": "Active",
        }, update_modified=False)
