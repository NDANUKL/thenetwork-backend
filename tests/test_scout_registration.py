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
            "frappe.rate_limiter": types.SimpleNamespace(rate_limit=lambda **kw: lambda fn: fn),
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

    def test_safe_codes_and_reference_without_private_error_logs(self):
        cases = [
            ({'full_name': 'One'}, 'INVALID_NAME'),
            ({'county': ''}, 'INVALID_COUNTY'),
            ({'password': 'short'}, 'INVALID_PASSWORD'),
            ({'phone': 'private-invalid'}, 'INVALID_PHONE'),
            ({'email': ''}, 'INVALID_EMAIL'),
        ]
        for changed, code in cases:
            self.frappe.response.clear()
            args = dict(full_name='Example Scout', email='synthetic@example.test', password='synthetic-password', county='Nairobi')
            args.update(changed)
            with self.assertRaises(ValueError):
                self.auth.register_field_agent(**args)
            self.assertEqual(self.frappe.response['diagnostic_code'], code)
            self.assertRegex(self.frappe.response['server_reference'], r'^REG-[a-f0-9]{32}$')
        self.frappe.log_error.assert_not_called()
        self.frappe.get_doc.assert_not_called()

    def test_duplicate_codes(self):
        for exists, code in [([True], 'APPLICATION_EXISTS'), ([False, True], 'ACCOUNT_EXISTS')]:
            self.frappe.response.clear()
            self.frappe.db.exists.side_effect = exists
            with self.assertRaises(ValueError):
                self.auth.register_field_agent('Example Scout', 'synthetic@example.test', 'synthetic-password', county='Nairobi')
            self.assertEqual(self.frappe.response['diagnostic_code'], code)

    def test_unexpected_failure_uses_deferred_safe_log_and_preserves_exception(self):
        self.frappe.db.exists.return_value = False
        failure = RuntimeError('private credentials synthetic@example.test')
        self.frappe.get_doc.side_effect = failure
        with self.assertRaises(RuntimeError) as caught:
            self.auth.register_field_agent('Example Scout', 'synthetic@example.test', 'synthetic-password', county='Nairobi')
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.frappe.response['diagnostic_code'], 'REGISTRATION_FAILED')
        logged = self.frappe.log_error.call_args.kwargs
        self.assertTrue(logged['defer_insert'])
        self.assertIn(self.frappe.response['server_reference'], logged['message'])
        self.assertIn('auth.py:', logged['message'])
        self.assertNotIn('credentials', logged['message'])
        self.assertNotIn('synthetic@', logged['message'])
        self.frappe.db.commit.assert_not_called()

    def test_login_records_activity_after_authentication(self):
        self.frappe.db.exists.return_value = "SCT-00001"
        outer=self
        class Manager:
            def login(self):
                self.user='scout@example.test';self.post_login()
            def post_login(self):
                outer.frappe.session.user=self.user
        self.frappe.auth.LoginManager=Manager
        self.frappe.form_dict={}
        self.frappe.flags=types.SimpleNamespace(dd_verified_mfa_user=None)
        two=types.SimpleNamespace(get_cached_user_pass=lambda:(None,None),should_run_2fa=lambda user:False)
        with patch.dict("sys.modules", {"frappe.utils":self.utils,"frappe.twofactor":two}):
            self.auth._login("scout@example.test", "password123")
        self.frappe.db.set_value.assert_called_once_with("Scout Profile", "SCT-00001", {
            "last_app_activity": "2026-10-18 12:00:00", "activity_status": "Active",
        }, update_modified=False)
