"""Offline regressions; real Frappe concurrency and sandbox acceptance remain required."""
import importlib.util
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parent
if not (ROOT / "payment_rules.py").exists():
    ROOT = ROOT.parent / "fieldpulse"
spec = importlib.util.spec_from_file_location("payment_rules_tested", ROOT / "payment_rules.py")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


class RulesTests(unittest.TestCase):
    def test_split_preserves_full_quote_and_rounds_odd_cent(self):
        self.assertEqual(rules.instalments("10000"), (Decimal("5000.00"), Decimal("5000.00")))
        self.assertEqual(rules.instalments("100.01"), (Decimal("50.01"), Decimal("50.00")))
        for total in ("0", "0.01", "NaN", "Infinity", "-1"):
            with self.assertRaises(ValueError):
                rules.instalments(total)

    def test_only_exact_provider_host(self):
        for url in ("http://pay.pesapal.com/a", "https://pay.pesapal.com.evil/a", "https://user@pay.pesapal.com/a", "https://pay.pesapal.com:444/a"):
            with self.assertRaises(ValueError):
                rules.checkout_url(url, "live")
        self.assertEqual(rules.checkout_url("https://cybqa.pesapal.com/order", "sandbox"), "https://cybqa.pesapal.com/order")

    def test_verified_payment_checks_reference_amount_currency_confirmation(self):
        good = dict(status="200", merchant_reference="DD-test", amount=50, currency="KES", status_code=1, confirmation_code="verified")
        self.assertEqual(rules.verified_status(good, "DD-test", 50, "KES"), "Paid")
        for changes in ({"amount": 49}, {"currency": "USD"}, {"merchant_reference": "other"}, {"confirmation_code": ""}, {"status_code": 9}, {"status": "500"}):
            with self.assertRaises(ValueError):
                rules.verified_status({**good, **changes}, "DD-test", 50, "KES")
        self.assertEqual(rules.verified_status({**good, "status_code": 3}, "DD-test", 50, "KES"), "Reversed")


class Record(dict):
    def __getattr__(self, name):
        return self.get(name)


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.whitelist = lambda **kwargs: lambda fn: fn
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.frappe.utils = types.SimpleNamespace(getdate=lambda value=None: value or "2026-10-14", now_datetime=lambda: "now")
        self.frappe.session.user = "customer@example.com"
        modules = {"frappe": self.frappe, "frappe.utils": self.frappe.utils, "fieldpulse.payment_rules": rules, "requests": MagicMock()}
        self.modules = patch.dict(sys.modules, modules)
        self.modules.start()
        spec = importlib.util.spec_from_file_location("payments_tested", ROOT / "payments.py")
        self.payments = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.payments)
        self.payments._lock = MagicMock()

    def tearDown(self):
        self.modules.stop()

    def test_unpaid_and_unaccepted_assignment_blocked(self):
        doc = Record(field_request="project", status="Assigned", scout_profile="scout", name="new")
        doc.is_new = lambda: True
        doc.get_doc_before_save = lambda: None
        self.frappe.db.get_value.return_value = "request"
        self.payments._quote = MagicMock(return_value=Record(name="quote", status="Issued"))
        with self.assertRaisesRegex(ValueError, "50% deposit"):
            self.payments.require_deposit(doc)
        self.payments._quote.return_value.status = "Accepted"
        self.payments._quote.return_value["status"] = "Accepted"
        self.frappe.db.exists.return_value = False
        with self.assertRaisesRegex(ValueError, "50% deposit"):
            self.payments.require_deposit(doc)

    def test_paid_assignment_enforces_project_scout_count(self):
        doc = Record(field_request="project", status="Assigned", scout_profile="scout-2", name="new")
        doc.is_new = lambda: True
        doc.get_doc_before_save = lambda: None
        self.frappe.db.get_value.return_value = "request"
        self.frappe.db.exists.return_value = True
        self.frappe.get_all.return_value = ["scout-1"]
        self.frappe.db.get_value.side_effect = ["request", "attempt", "live", "request", "attempt", "live"]
        quote = Record(name="quote", status="Accepted")
        # Dict.items conflicts with attribute access; real Frappe documents don't.
        quote.items = [Record(field_request="project", planned_scouts=1)]
        self.payments._quote = MagicMock(return_value=quote)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.payments.require_deposit(doc)
        quote.items[0]["planned_scouts"] = 2
        self.payments.require_deposit(doc)

    def test_acceptance_creates_two_linked_obligations_only_once(self):
        self.payments._owned = MagicMock(return_value=Record(name="request"))
        quote = Record(name="quote", status="Issued", version=1, valid_until="2026-12-01", deposit_amount=50, total=100, currency="KES")
        self.payments._quote = MagicMock(return_value=quote)
        self.payments.accept_quote("request", "quote", 1, "retry-key")
        created = [call.args[0] for call in self.frappe.get_doc.call_args_list]
        self.assertEqual([row["kind"] for row in created], ["deposit", "balance"])
        self.assertTrue(all(row["quotation"] == "quote" and row["amount"] == 50 for row in created))
        quote["status"] = "Accepted"
        self.frappe.get_doc.reset_mock()
        self.payments.accept_quote("request", "quote", 1, "retry-key")
        self.frappe.get_doc.assert_not_called()

    def test_wrong_provider_amount_cannot_mark_paid(self):
        attempt = Record(name="attempt", tracking_id="tracking", environment="sandbox", merchant_reference="ref", amount=50, currency="KES")
        self.frappe.get_doc.return_value = attempt
        self.payments._config = MagicMock(return_value=("sandbox",))
        self.payments._provider = MagicMock(return_value=dict(status="200", merchant_reference="ref", amount=49, currency="KES", status_code=1, confirmation_code="code"))
        with self.assertRaises(ValueError):
            self.payments._verify("attempt")
        self.frappe.db.set_value.assert_not_called()

    def test_pending_notification_does_not_undo_paid_payment(self):
        attempt = Record(name="attempt", tracking_id="tracking", environment="sandbox", merchant_reference="ref", amount=50, currency="KES", payment="payment", status="Paid")
        attempt.reload = lambda: None
        payment = Record(name="payment", request="request", status="Paid")
        payment.reload = lambda: None
        self.frappe.get_doc.side_effect = [attempt, payment]
        self.payments._config = MagicMock(return_value=("sandbox",))
        self.payments._provider = MagicMock(return_value=dict(status="200", merchant_reference="ref", amount=50, currency="KES", status_code=0))
        self.payments._verify("attempt")
        self.frappe.db.set_value.assert_not_called()

    def test_balance_cannot_be_paid_before_completion(self):
        self.payments._owned = MagicMock(return_value=Record(name="request", status="In Progress"))
        self.payments._quote = MagicMock(return_value=Record(name="quote", status="Accepted"))
        self.frappe.get_doc.return_value = Record(name="payment", request="request", quotation="quote", kind="balance", status="Unpaid")
        with self.assertRaisesRegex(ValueError, "after completion"):
            self.payments.checkout("request", "payment", "retry")
        self.frappe.db.commit.assert_not_called()

    def test_pending_checkout_is_reused_without_another_provider_order(self):
        self.payments._owned = MagicMock(return_value=Record(name="request"))
        self.payments._quote = MagicMock(return_value=Record(name="quote", status="Accepted"))
        obligation = Record(name="payment", request="request", quotation="quote", kind="deposit", status="Unpaid", currency="KES")
        attempt = Record(name="attempt", environment="sandbox", checkout_url="https://cybqa.pesapal.com/order")
        self.frappe.get_doc.side_effect = [obligation, attempt]
        self.frappe.db.get_value.return_value = "attempt"
        self.frappe.conf.get.return_value = ["KES"]
        self.payments._config = MagicMock(return_value=("sandbox", "https://test.example", "key", "secret", "ipn", "base"))
        self.payments._provider = MagicMock()
        self.assertEqual(self.payments.checkout("request", "payment", "retry"), {"checkout_url": attempt.checkout_url})
        self.payments._provider.assert_not_called()

    def test_sandbox_collection_requires_explicit_test_dispatch_enablement(self):
        doc = Record(field_request="project", status="Assigned", scout_profile="scout", name="new")
        doc.is_new = lambda: True
        doc.get_doc_before_save = lambda: None
        self.frappe.db.get_value.side_effect = ["request", "attempt", "sandbox"]
        self.frappe.db.exists.return_value = True
        self.frappe.conf.get.return_value = False
        self.frappe.db.get_single_value.return_value = False
        self.payments._quote = MagicMock(return_value=Record(name="quote", status="Accepted"))
        with self.assertRaisesRegex(ValueError, "live verified deposit"):
            self.payments.require_deposit(doc)

    def test_notification_verification_failure_returns_retry_not_paid(self):
        self.frappe.response = {}
        self.frappe.db.get_value.return_value = "attempt"
        self.frappe.get_doc.return_value = Record(tracking_id="tracking")
        self.payments._verify = MagicMock(side_effect=ValueError("Provider unavailable"))
        self.payments.ipn("tracking", "reference", "IPNCHANGE")
        self.assertEqual(self.frappe.response["status"], 500)
        self.frappe.db.rollback.assert_called_once()
        self.frappe.db.commit.assert_not_called()
        self.frappe.db.set_value.assert_not_called()

    def test_verified_payment_records_provider_evidence_and_pays_obligation(self):
        attempt = Record(name="attempt", tracking_id="tracking", environment="sandbox", merchant_reference="ref", amount=50, currency="KES", payment="payment", status="Pending")
        attempt.reload = lambda: None
        payment = Record(name="payment", request="request", status="Unpaid")
        payment.reload = lambda: None
        self.frappe.get_doc.side_effect = [attempt, payment]
        self.payments._config = MagicMock(return_value=("sandbox",))
        self.payments._provider = MagicMock(return_value=dict(status="200", merchant_reference="ref", amount=50, currency="KES", status_code=1, confirmation_code="confirmation"))
        self.payments._verify("attempt")
        writes = self.frappe.db.set_value.call_args_list
        self.assertEqual(writes[0].args[2]["status"], "Paid")
        self.assertEqual(writes[0].args[2]["confirmation_code"], "confirmation")
        self.assertEqual(writes[1].args[2]["paid_attempt"], "attempt")
        self.assertEqual(writes[1].args[2]["status"], "Paid")


if __name__ == "__main__":
    unittest.main()
