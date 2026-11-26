import json
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.db.sql.return_value = []
        self.frappe.whitelist.side_effect = lambda **kw: lambda fn: fn
        spec = importlib.util.spec_from_file_location("feedback_under_test", Path(__file__).resolve().parents[1] / "fieldpulse/beta_feedback.py")
        self.module = importlib.util.module_from_spec(spec)
        access = types.ModuleType("fieldpulse.beta_access")
        access.require_access = MagicMock()
        with patch.dict(sys.modules, {"frappe": self.frappe, "fieldpulse.beta_access": access}):
            spec.loader.exec_module(self.module)
        self.original_bridge = self.module.bridge_account
        self.access = access
        self.module.bridge_account = MagicMock(return_value=("ACCOUNT-1", types.SimpleNamespace(name="client@example.com", full_name="Client Name")))
        self.answers = dict(understanding="Checks my plot", legitimacy="Legit", confusing="No", proof_trust="5", scout_comfort="3", trust_more="Independent review", deposit="Unsure", pricing_clear="Yes", fair_price="100.50", currency="USD", would_use="Maybe", use_case="Check a plot", recommend="0", nearly_stopped="Nothing", country_of_residence="Kenya")

    def dispatch(self, action="submit", answers=None, slot=0):
        self.frappe.form_dict = dict(email="client@example.com", action=action, response_slot=slot,
                                    answers=answers if answers is not None else self.answers)
        return self.module.dispatch()

    def test_country_is_required_and_validated(self):
        missing = dict(self.answers)
        missing.pop("country_of_residence")
        with self.assertRaises(ValueError):
            self.module.validate_answers(missing)
        self.assertEqual(self.module.validate_answers(dict(self.answers, country_of_residence=" United Kingdom "))["country_of_residence"], "United Kingdom")
        for value in ("", "   ", None, [], 123, "x" * 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module.validate_answers(dict(self.answers, country_of_residence=value))

    def test_valid_answer_types_and_zero_recommendation(self):
        result = self.module.validate_answers(self.answers)
        self.assertEqual(result["recommend"], 0)
        self.assertEqual(result["fair_price"], "100.50")

    def test_invalid_and_conditional_answers(self):
        for key, value in [("legitimacy", "Bad"), ("confusing", "Yes"), ("currency", "Other"), ("proof_trust", "6"), ("recommend", True), ("recommend", "-1"), ("fair_price", "NaN"), ("fair_price", "-1"), ("fair_price", "1.001"), ("understanding", " "), ("use_case", ""), ("trust_more", "x"*2001)]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                self.module.validate_answers({**self.answers, key:value})

    def test_v2_pricing_requires_three_prices_and_supported_currencies(self):
        answers = dict(self.answers, form_version="2")
        answers.pop("fair_price")
        answers.pop("currency")
        fields = ("land_property_price", "construction_price", "business_asset_price")
        for field in fields:
            answers[field] = "25.50"
            answers[field + "_currency"] = "USD"
        result = self.module.validate_answers(answers)
        self.assertNotIn("fair_price", result)
        for field in fields:
            self.assertEqual(result[field], "25.50")
            for value in (None, "", True, "NaN", "-1", "0.001"):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.module.validate_answers(dict(answers, **{field: value}))
            for currency in ("GBP", "Other", "", None):
                with self.subTest(currency=currency), self.assertRaises(ValueError):
                    self.module.validate_answers(dict(answers, **{field + "_currency": currency}))
        self.assertEqual(self.module.validate_answers(dict(answers, land_property_price="0", land_property_price_currency="KES"))["land_property_price"], "0")
        result = self.module.validate_answers(dict(answers, pricing_clear="No"))
        self.assertTrue(all(field not in result and field + "_currency" not in result for field in fields))

    def test_other_feedback_is_optional_for_v2(self):
        answers = dict(self.answers, form_version="2", pricing_clear="No")
        del answers["nearly_stopped"]
        self.assertEqual(self.module.validate_answers(answers)["nearly_stopped"], "")
        self.assertEqual(self.module.validate_answers(dict(answers, nearly_stopped=" More examples "))["nearly_stopped"], "More examples")

    def test_no_request_is_ineligible(self):
        self.frappe.db.exists.return_value = None
        self.assertEqual(self.dispatch(), {"not_eligible": True})
        self.frappe.get_doc.assert_not_called()

    def test_repeat_submission_returns_success_without_overwriting(self):
        self.frappe.db.exists.return_value = "EXISTS"
        self.frappe.db.sql.side_effect = [[("ACCOUNT-1",)], [("FEEDBACK-1",)]]
        self.assertEqual(self.dispatch(), {"eligible": True, "submitted": True, "response_count": 1})
        self.frappe.get_doc.assert_not_called()
        self.assertIn("tabDD Customer Account", self.frappe.db.sql.call_args_list[0].args[0])
        self.assertIn("tabDD Beta Feedback", self.frappe.db.sql.call_args_list[1].args[0])
        self.assertIn("FOR UPDATE", self.frappe.db.sql.call_args_list[1].args[0])
        self.assertFalse(any(call.args[0] == "DD Beta Feedback" for call in self.frappe.db.exists.call_args_list))

    def test_second_response_uses_the_last_slot_and_retries_do_not_insert(self):
        self.frappe.db.exists.return_value = "REQUEST-1"
        self.frappe.db.sql.side_effect = [
            [("ACCOUNT-1",)], [("FEEDBACK-1",)],
            [("ACCOUNT-1",)], [("FEEDBACK-1",), ("FEEDBACK-2",)],
        ]
        result = {"eligible": True, "submitted": True, "response_count": 2}
        self.assertEqual(self.dispatch(slot="1"), result)
        self.assertEqual(self.dispatch(slot="1"), result)
        self.assertEqual(self.dispatch(slot=2), {"invalid": True})
        self.frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

    def test_cannot_skip_the_first_response(self):
        self.frappe.db.exists.return_value = "REQUEST-1"
        self.assertEqual(self.dispatch(slot=1), {"invalid": True})
        self.frappe.get_doc.assert_not_called()

    def test_submission_binds_server_identity_time_and_ignores_forged_fields(self):
        self.frappe.db.exists.return_value = "REQUEST-1"
        self.assertTrue(self.dispatch(answers={**self.answers, "customer_email":"attacker@example.com", "customer_account":"OTHER", "submitted_at_utc":"2000-01-01"})["submitted"])
        stored = self.frappe.get_doc.call_args.args[0]
        self.assertEqual(stored["customer_email"], "client@example.com")
        self.assertEqual(stored["customer_account"], "ACCOUNT-1")
        self.assertEqual(stored["customer_name"], "Client Name")
        self.assertTrue(stored["submitted_at_utc"].endswith("Z"))
        self.assertEqual(int(stored["submitted_at_utc"][:4]), self.module.datetime.now(self.module.timezone.utc).year)
        self.frappe.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

    def test_status_does_not_lock_or_write(self):
        self.frappe.db.exists.return_value = "REQUEST-1"
        for count in (0, 1, 2):
            self.frappe.db.count.return_value = count
            self.assertEqual(self.dispatch("status"), {
                "eligible": True, "submitted": count == 2, "response_count": count,
            })
        self.frappe.db.sql.assert_not_called()
        self.frappe.get_doc.assert_not_called()

    def test_invalid_payload_does_not_insert(self):
        self.frappe.db.exists.return_value = "REQUEST-1"
        self.assertEqual(self.dispatch(answers={}), {"invalid":True})
        self.frappe.get_doc.assert_not_called()

    def test_bridge_rejects_direct_customer_session(self):
        del self.module.bridge_account
        self.frappe.get_roles.return_value = ["DD Customer"]
        self.frappe.throw.side_effect = PermissionError
        # Reload original function without replacing the validation dependencies.
        spec = importlib.util.spec_from_file_location("bridge_test", Path(__file__).resolve().parents[1] / "fieldpulse/beta_feedback.py")
        original = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"frappe":self.frappe,"fieldpulse.beta_access":types.SimpleNamespace(require_access=MagicMock())}):
            spec.loader.exec_module(original)
        with self.assertRaises(PermissionError): original.bridge_account("client@example.com")


    def test_bridge_checks_verified_active_customer_without_desk_roles(self):
        self.frappe.get_roles.return_value = ["System Manager"]
        self.frappe.throw.side_effect = PermissionError
        user = types.SimpleNamespace(name="client@example.com", full_name="Client", enabled=1, user_type="Website User", roles=[types.SimpleNamespace(role="DD Customer")])
        self.frappe.db.exists.return_value = "ACCOUNT-1"
        self.frappe.get_doc.return_value = user
        self.frappe.db.get_value.return_value = 0
        self.assertEqual(self.original_bridge("CLIENT@example.com"), ("ACCOUNT-1", user))
        self.access.require_access.assert_called_once_with("ACCOUNT-1")
        self.frappe.db.exists.assert_called_with("DD Customer Account", {"user":"client@example.com", "email_verified":1})
        for enabled, user_type, roles, desk in [(0,"Website User",["DD Customer"],0), (1,"System User",["DD Customer"],0), (1,"Website User",[],0), (1,"Website User",["DD Customer","Staff"],1)]:
            with self.subTest(enabled=enabled,user_type=user_type,roles=roles):
                user.enabled=enabled;user.user_type=user_type;user.roles=[types.SimpleNamespace(role=role) for role in roles]
                self.frappe.db.get_value.return_value=desk
                with self.assertRaises(PermissionError): self.original_bridge("client@example.com")
        self.frappe.db.exists.return_value = None
        with self.assertRaises(PermissionError): self.original_bridge("client@example.com")

    def test_unapproved_or_deactivated_customer_is_denied(self):
        self.frappe.get_roles.return_value = ["System Manager"]
        self.frappe.db.exists.return_value = "ACCOUNT-1"
        self.frappe.get_doc.return_value = types.SimpleNamespace(enabled=1, user_type="Website User", roles=[types.SimpleNamespace(role="DD Customer")])
        self.frappe.db.get_value.return_value = 0
        self.access.require_access.side_effect = PermissionError
        with self.assertRaises(PermissionError): self.original_bridge("client@example.com")

    def test_feedback_controller_blocks_updates_manual_creation_and_deletion(self):
        spec = importlib.util.spec_from_file_location("feedback_controller", Path(__file__).resolve().parents[1] / "fieldpulse/fieldpulse/doctype/dd_beta_feedback/dd_beta_feedback.py")
        controller = importlib.util.module_from_spec(spec)
        self.frappe.throw.side_effect = PermissionError
        with patch.dict(sys.modules, {"frappe":self.frappe,"frappe.model":types.ModuleType("frappe.model"),"frappe.model.document":types.SimpleNamespace(Document=object)}):
            spec.loader.exec_module(controller)
        document = controller.DDBetaFeedback()
        document.flags = {}
        document.is_new = lambda: True
        with self.assertRaises(PermissionError): document.validate()
        document.flags = {"beta_feedback_submission":True}
        document.validate()
        document.is_new = lambda: False
        with self.assertRaises(PermissionError): document.validate()
        with self.assertRaises(PermissionError): document.on_trash()



    def test_maximum_length_answers_allow_json_escaping(self):
        answers = {**self.answers, "confusing":"Yes", "confusing_details":"x", "use_case":"x"}
        for key in ("understanding", "trust_more", "nearly_stopped", "confusing_details", "use_case"):
            answers[key] = "\\" * 2000
        encoded = json.dumps(answers)
        self.assertGreater(len(encoded), 18000)
        result = self.module.validate_answers(encoded)
        self.assertEqual(result["understanding"], answers["understanding"])


if __name__ == "__main__": unittest.main()
