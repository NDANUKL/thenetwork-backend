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

    def test_discount_then_vat_and_payment_split(self):
        totals = rules.quotation_totals(200, "Percentage", 10)
        self.assertEqual(totals, dict(subtotal=Decimal("200"), discount_amount=Decimal("20"), taxable_amount=Decimal("180"), vat_amount=Decimal("28.80"), total=Decimal("208.80")))
        self.assertEqual(rules.instalments(totals['total']), (Decimal("104.40"), Decimal("104.40")))
        self.assertEqual(rules.quotation_totals(200, "Fixed amount", 20), totals)
        self.assertEqual(rules.quotation_totals(100)['total'], Decimal("116"))

    def test_inclusive_prices_extract_vat_after_discount(self):
        totals = rules.quotation_totals(232, "Fixed amount", 116, 16, True)
        self.assertEqual(totals['taxable_amount'], Decimal("100"))
        self.assertEqual(totals['vat_amount'], Decimal("16"))
        self.assertEqual(totals['total'], Decimal("116"))
        self.assertEqual(rules.quotation_totals("100.01", vat_rate=0)['total'], Decimal("100.01"))

    def test_invalid_discounts_and_tax_rejected(self):
        for kwargs in [dict(discount_type="Percentage", discount_value=101), dict(discount_type="Fixed amount", discount_value=101), dict(discount_value=5), dict(discount_type="other"), dict(vat_rate=101), dict(vat_rate="NaN"), dict(discount_value=-1), dict(discount_type="Percentage", discount_value=100)]:
            with self.assertRaises(ValueError):
                rules.quotation_totals(100, **kwargs)

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

    def test_quotation_download_requires_request_ownership(self):
        self.payments._owned = MagicMock(side_effect=PermissionError("Not yours"))
        self.frappe.get_print = MagicMock()
        with self.assertRaises(PermissionError):
            self.payments.download_quote("someone-elses-request")
        self.frappe.get_print.assert_not_called()

    def test_quotation_download_prints_only_current_owned_quote(self):
        self.payments._owned = MagicMock(return_value=Record(name="request"))
        current = Record(name="quote", status="Accepted")
        self.payments._quote = MagicMock(return_value=current)
        pdf = types.ModuleType('frappe.utils.pdf')
        pdf.get_pdf = MagicMock(return_value=b'%PDF-test')
        self.frappe.get_doc.return_value = Record(html='<p>Quotation</p>')
        self.frappe.render_template.return_value = '<p>Rendered</p>'
        self.frappe.response = {}
        with patch('fieldpulse.quotation_pdf.render_quotation_pdf', return_value=b'%PDF-test') as render_pdf:
            self.payments.download_quote("request")
        render_pdf.assert_called_once()
        render_context = self.frappe.render_template.call_args.args[1]
        self.assertIs(render_context['doc'], current)
        self.assertTrue(render_context['quotation_assets']['logo'].startswith('data:image/png;base64,'))
        self.assertTrue(render_context['quotation_assets']['regular'].startswith('data:font/ttf;base64,'))
        self.assertIn('<p>Rendered</p>', render_pdf.call_args.args[0])
        self.assertEqual(self.frappe.response['filecontent'], b"%PDF-test")

    def quote_document(self):
        doc = Record(name='draft', request='request', status='Draft', currency='USD', quotation_date='2026-10-14', valid_until='2026-11-14', discount_type='Percentage', discount_value=10, vat_rate=16)
        doc.get_doc_before_save = lambda: None
        doc.items = [Record(field_request='project-1', quantity=1, rate=100, description='Scope one', planned_scouts=1), Record(field_request='project-2', quantity=1, rate=100, description='Scope two', planned_scouts=1)]
        request = Record(name='request', full_name='Client', email='client@example.com')
        request.check_permission = MagicMock()
        self.frappe.get_doc.side_effect = lambda dt, name: request if dt == 'Diaspora Request' else Record(name=name, diaspora_request='request', project_title=name, field_brief='Confirmed scope for ' + name)
        self.frappe.db.exists.return_value = False
        return doc

    def test_beta_quote_charges_one_shilling_per_project_including_vat(self):
        doc = self.quote_document()
        doc['pricing_mode'] = 'Beta - KSh 1 per project'
        doc['discount_value'] = 0
        doc['discount_type'] = 'Fixed amount'
        self.payments.validate_quote(doc)
        self.assertEqual(doc.currency, 'KES')
        self.assertEqual(doc.total, 2)
        self.assertEqual(doc.tax_inclusive, 1)
        self.assertEqual(doc.deposit_amount, 1)
        self.assertEqual(doc.balance_amount, 1)
        self.assertTrue(all(item.rate == 1 and item.amount == 1 for item in doc.items))

    def test_beta_single_project_and_live_switch(self):
        doc = self.quote_document()
        doc.items = doc.items[:1]
        doc['pricing_mode'] = 'Beta - KSh 1 per project'
        doc['discount_value'] = 0
        self.payments.validate_quote(doc)
        self.assertEqual((doc.total, doc.deposit_amount, doc.balance_amount), (1, .5, .5))
        doc['pricing_mode'] = 'Live - USD 100 per project'
        self.payments.validate_quote(doc)
        self.assertEqual((doc.currency, doc.total, doc.tax_inclusive), ('USD', 116, 0))

    def test_invalid_pricing_and_legacy_currency_are_not_silently_repriced(self):
        doc = self.quote_document()
        doc['pricing_mode'] = 'Free'
        with self.assertRaisesRegex(ValueError, 'Select Beta'):
            self.payments.validate_quote(doc)
        doc['pricing_mode'] = None
        doc['currency'] = 'KES'
        with self.assertRaisesRegex(ValueError, 'explicitly'):
            self.payments.validate_quote(doc)

    def test_pricing_cannot_change_issued_or_accepted_quotes(self):
        for status in ('Issued', 'Accepted'):
            doc = self.quote_document()
            doc['pricing_mode'] = 'Beta - KSh 1 per project'
            doc.get_doc_before_save = lambda: Record(status=status)
            with self.assertRaisesRegex(ValueError, 'locked'):
                self.payments.validate_quote(doc)

    def test_quote_deadline_comes_from_linked_projects(self):
        doc = self.quote_document()
        original = self.frappe.get_doc.side_effect
        def documents(dt, name):
            result = original(dt, name)
            if dt == 'Field Request':
                result['deadline'] = '2026-11-03' if name == 'project-1' else '2026-11-07'
            return result
        self.frappe.get_doc.side_effect = documents
        doc.agreed_completion_date = '2030-01-01'
        self.payments.validate_quote(doc)
        self.assertEqual(str(doc.agreed_completion_date), '2026-11-07')
        self.assertEqual(doc.items[0].agreed_work_deadline, '2026-11-03')
        self.assertEqual(doc.items[1].agreed_work_deadline, '2026-11-07')

    def test_new_quote_always_adds_vat_on_top(self):
        doc = self.quote_document()
        doc['tax_inclusive'] = 1
        doc['discount_type'] = 'Fixed amount'
        doc['discount_value'] = 0
        self.payments.validate_quote(doc)
        self.assertEqual(doc.tax_inclusive, 0)
        self.assertEqual(doc.subtotal, 200)
        self.assertEqual(doc.vat_amount, 32)
        self.assertEqual(doc.total, 232)

    def test_multi_project_quote_uses_combined_discounted_total(self):
        doc = self.quote_document()
        self.payments.validate_quote(doc)
        self.assertEqual(doc.subtotal, 200)
        self.assertEqual(doc.discount_amount, 20)
        self.assertEqual(doc.vat_amount, 28.8)
        self.assertEqual(doc.total, 208.8)
        self.assertEqual(doc.deposit_amount + doc.balance_amount, doc.total)

    def test_fixed_discount_shows_equivalent_percentage(self):
        doc = self.quote_document()
        doc['discount_type'] = 'Fixed amount'
        doc['discount_value'] = 40
        self.payments.validate_quote(doc)
        self.assertEqual(doc.discount_amount, 40)
        self.assertEqual(doc.discount_percentage, 20)
        self.assertEqual(doc.discount_type, 'Fixed amount')

    def test_percentage_draft_converts_without_changing_discount(self):
        doc = self.quote_document()
        self.payments.validate_quote(doc)
        self.assertEqual(doc.discount_type, 'Fixed amount')
        self.assertEqual(doc.discount_value, 20)
        self.assertEqual(doc.discount_percentage, 10)
        self.assertEqual(doc.total, 208.8)

    def test_fixed_discount_percentage_rounds_to_two_decimals(self):
        doc = self.quote_document()
        doc['discount_type'] = 'Fixed amount'
        doc['discount_value'] = 33.33
        self.payments.validate_quote(doc)
        self.assertEqual(doc.discount_percentage, 16.67)

    def test_quotation_scope_comes_from_linked_project(self):
        doc = self.quote_document()
        doc.items[0]['description'] = 'Manually overridden scope'
        self.payments.validate_quote(doc)
        self.assertEqual(doc.items[0].description, 'Confirmed scope for project-1')
        self.assertEqual(doc.items[1].description, 'Confirmed scope for project-2')

    def test_quotation_requires_existing_project_brief(self):
        doc = self.quote_document()
        request = Record(name='request', full_name='Client', email='client@example.com', check_permission=MagicMock())
        self.frappe.get_doc.side_effect = lambda dt, name: request if dt == 'Diaspora Request' else Record(name=name, diaspora_request='request', field_brief=' ')
        with self.assertRaisesRegex(ValueError, 'linked project brief'):
            self.payments.validate_quote(doc)

    def test_quotation_rejects_duplicate_or_unrelated_projects(self):
        doc = self.quote_document()
        doc.items[1]['field_request'] = 'project-1'
        with self.assertRaisesRegex(ValueError, 'each quoted project once'):
            self.payments.validate_quote(doc)
        doc = self.quote_document()
        self.frappe.get_doc.side_effect = [Record(name='request', check_permission=MagicMock()), Record(name='foreign-project', diaspora_request='another-request')]
        with self.assertRaisesRegex(ValueError, 'each quoted project once'):
            self.payments.validate_quote(doc)

    def test_project_price_is_fixed_in_usd(self):
        doc = self.quote_document()
        doc.items[0]['rate'] = 999
        doc.items[0]['quantity'] = 3
        self.payments.validate_quote(doc)
        self.assertEqual(doc.items[0].rate, 100)
        self.assertEqual(doc.items[0].quantity, 1)
        self.assertEqual(doc.items[0].amount, 100)
        self.assertEqual(doc.subtotal, 200)

    def test_non_usd_draft_is_not_silently_converted(self):
        doc = self.quote_document()
        doc['currency'] = 'KES'
        with self.assertRaisesRegex(ValueError, 'explicitly'):
            self.payments.validate_quote(doc)

    def test_issued_quote_gets_standard_terms_automatically(self):
        doc = self.quote_document()
        doc['status'] = 'Issued'
        self.payments.validate_quote(doc)
        self.assertIn('Pay 50% upfront', doc.terms)
        self.assertIn('approved report', doc.terms)

    def test_existing_issued_quotation_is_not_repriced(self):
        doc = self.quote_document()
        doc.get_doc_before_save = lambda: Record(status='Accepted')
        with self.assertRaisesRegex(ValueError, 'locked'):
            self.payments.validate_quote(doc)

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
        self.frappe.db.get_single_value.return_value = "live"
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

    def test_balance_requires_a_published_report_even_after_completed_fieldwork(self):
        self.payments._owned = MagicMock(return_value=Record(name="request", status="Completed"))
        self.payments._quote = MagicMock(return_value=Record(name="quote", status="Accepted"))
        self.frappe.get_doc.return_value = Record(name="payment", request="request", quotation="quote", kind="balance", status="Unpaid")
        self.frappe.db.exists.side_effect = lambda dt, filters: dt == "DD Payment"
        with self.assertRaisesRegex(ValueError, "approved report"):
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

    def test_dispatch_requires_deposit_in_current_environment(self):
        doc = Record(field_request="project", status="Assigned", scout_profile="scout", name="new")
        doc.is_new = lambda: True
        doc.get_doc_before_save = lambda: None
        quote = Record(name="quote", status="Accepted")
        quote.items = [Record(field_request="project", planned_scouts=1)]
        self.payments._quote = MagicMock(return_value=quote)
        self.frappe.db.exists.return_value = True
        self.frappe.get_all.return_value = []
        for mode, paid_mode, allowed in [("sandbox", "sandbox", True), ("live", "live", True), ("live", "sandbox", False), ("sandbox", "live", False), (None, "sandbox", False), ("live", None, False)]:
            with self.subTest(mode=mode, paid_mode=paid_mode):
                self.frappe.db.get_value.side_effect = ["request", "attempt", paid_mode]
                self.frappe.db.get_single_value.return_value = mode
                if allowed:
                    self.payments.require_deposit(doc)
                else:
                    with self.assertRaisesRegex(ValueError, "current payment environment"):
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
        with patch("fieldpulse.customer_notifications.queue_event") as queue:
            self.payments._verify("attempt")
        queue.assert_called_once_with("payment", payment)
        writes = self.frappe.db.set_value.call_args_list
        self.assertEqual(writes[0].args[2]["status"], "Paid")
        self.assertEqual(writes[0].args[2]["confirmation_code"], "confirmation")
        self.assertEqual(writes[1].args[2]["paid_attempt"], "attempt")
        self.assertEqual(writes[1].args[2]["status"], "Paid")


if __name__ == "__main__":
    unittest.main()
