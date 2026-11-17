"""One verified whole-KES receipt may settle two instalments, never twice."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import test_payments as fixture


class KesAllocationTests(unittest.TestCase):
    def setUp(self):
        fixture.FlowTests.setUp(self)
        R = fixture.Record
        self.deposit = R(name='deposit', request='request', quotation='quote', kind='deposit',
            amount=.5, currency='KES', status='Unpaid', paid_attempt=None)
        self.balance = R(name='balance', request='request', quotation='quote', kind='balance',
            amount=.5, currency='KES', status='Unpaid', paid_attempt=None)
        self.attempt = R(name='attempt', payment='deposit', amount=.5, currency='KES',
            tracking_id='tracking', merchant_reference='merchant', environment='live', status='Pending')
        self.quote = R(name='quote', request='request', currency='KES', status='Accepted', total=1)
        for doc in (self.deposit, self.balance, self.attempt): doc.reload = lambda: None
        self.docs = {'deposit': self.deposit, 'balance': self.balance, 'attempt': self.attempt, 'quote': self.quote}
        self.frappe.get_doc.side_effect = lambda dt, name: self.docs[name]
        self.frappe.db.exists.return_value = False
        def write(dt, name, values, value=None):
            self.docs[name].update(values if isinstance(values, dict) else {values: value})
        self.frappe.db.set_value.side_effect = write
        self.payments._obligations = MagicMock(return_value=[self.deposit, self.balance])
        self.payments._config = MagicMock(return_value=('live',))
        self.data = dict(status='200', status_code=1, amount=1, currency='KES',
            merchant_reference='merchant', payment_method='Mpesa', confirmation_code='confirmation')
        self.payments._provider = MagicMock(side_effect=lambda *args, **kwargs: dict(self.data))
        self.notifications = patch('fieldpulse.customer_notifications.queue_event')
        self.queue = self.notifications.start()

    def tearDown(self):
        self.notifications.stop()
        fixture.FlowTests.tearDown(self)

    def test_legacy_mpesa_receipt_settles_both_and_preserves_quote_and_original_amount(self):
        self.assertEqual(self.payments._verify('attempt'), 'Paid')
        self.assertEqual(self.quote.total, 1)
        self.assertEqual(self.attempt.amount, .5)
        self.assertEqual(self.attempt.received_amount, 1)
        self.assertEqual(self.attempt.balance_allocated, .5)
        self.assertEqual(self.attempt.balance_payment, 'balance')
        self.assertIsNone(self.attempt.reconcile_error_code)
        for doc in (self.deposit, self.balance):
            self.assertEqual(doc.amount, .5)
            self.assertEqual(doc.status, 'Paid')
            self.assertEqual(doc.paid_attempt, 'attempt')
        self.assertEqual(self.queue.call_count, 2)
        self.assertEqual(self.payments._lock.call_args_list[0].args, ('Diaspora Request', 'request'))
        self.frappe.db.commit.assert_not_called()

    def test_live_mpesake_receipt_settles_both_instalments(self):
        # Live status query for the affected legacy order returned this method.
        self.data['payment_method'] = 'MpesaKE'
        self.assertEqual(self.payments._verify('attempt'), 'Paid')
        self.assertEqual(self.attempt.amount, .5)
        self.assertEqual(self.attempt.received_amount, 1)
        for target in (self.deposit, self.balance):
            self.assertEqual(target.status, 'Paid')
            self.assertEqual(target.paid_attempt, 'attempt')
        self.payments._verify('attempt')
        self.assertEqual(self.queue.call_count, 2)

    def test_unknown_mpesa_suffix_cannot_enable_legacy_rounding(self):
        for method in ('MpesaKE-other', 'MpesaTZ', 'MpesaKEVisa', ''):
            with self.subTest(method=method):
                self.data['payment_method'] = method
                with self.assertRaises(ValueError):
                    self.payments._verify('attempt')
                self.frappe.db.set_value.assert_not_called()
        self.queue.assert_not_called()

    def test_both_allocations_are_valid_before_notifications_are_captured(self):
        spec = importlib.util.spec_from_file_location('allocation_notification_receipts',
            Path(fixture.ROOT) / 'payment_receipts.py')
        receipts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(receipts)
        def capture(kind, payment):
            # The real queue_event discards events without a verified receipt.
            self.assertIs(receipts.verified_attempt(payment), self.attempt)
        self.queue.side_effect = capture
        self.payments._verify('attempt')
        self.assertEqual(self.queue.call_count, 2)

    def test_repeated_callback_allocates_and_notifies_only_once(self):
        self.payments._verify('attempt')
        self.payments._verify('attempt')
        self.assertEqual(self.queue.call_count, 2)
        self.assertEqual(self.deposit.amount + self.balance.amount, self.attempt.received_amount)

    def test_callback_started_before_allocation_revalidates_after_lock(self):
        # Another callback allocates both instalments while this provider query
        # is in flight. Its stale half-shilling result must not overwrite it.
        self.data['amount'] = .5
        def allocated_while_waiting():
            self.attempt.update(status='Paid', balance_payment='balance',
                balance_allocated=.5, received_amount=1)
            for target in (self.deposit, self.balance):
                target.update(status='Paid', paid_attempt='attempt', paid_at='now')
        self.attempt.reload = allocated_while_waiting
        with self.assertRaises(ValueError):
            self.payments._verify('attempt')
        self.frappe.db.set_value.assert_not_called()
        self.queue.assert_not_called()

    def test_reversal_reverses_both_allocations(self):
        self.payments._verify('attempt')
        self.data['status_code'] = 3
        self.assertEqual(self.payments._verify('attempt'), 'Reversed')
        self.assertEqual(self.deposit.status, 'Reversed')
        self.assertEqual(self.balance.status, 'Reversed')

    def test_stale_pending_or_failed_callback_cannot_erase_verified_payment(self):
        self.payments._verify('attempt')
        for state in (0, 2):
            self.data['status_code'] = state
            self.assertEqual(self.payments._verify('attempt'), 'Paid')
            self.assertEqual(self.balance.status, 'Paid')

    def test_other_amount_currency_reference_method_and_missing_confirmation_fail_closed(self):
        for field, value in [('amount', .75), ('amount', 2), ('currency', 'USD'),
                             ('merchant_reference', 'foreign'), ('payment_method', 'Visa'),
                             ('confirmation_code', ''), ('status', '500')]:
            with self.subTest(field=field, value=value):
                original = self.data[field]
                self.data[field] = value
                with self.assertRaises(ValueError): self.payments._verify('attempt')
                self.frappe.db.set_value.assert_not_called()
                self.data[field] = original

    def test_wrong_quotation_request_total_and_already_allocated_balance_fail_closed(self):
        for doc, field, value in [(self.balance, 'request', 'foreign'),
                                  (self.balance, 'quotation', 'other-quote'),
                                  (self.quote, 'total', 2), (self.quote, 'status', 'Withdrawn'),
                                  (self.balance, 'paid_attempt', 'other-attempt'),
                                  (self.deposit, 'paid_attempt', 'other-attempt')]:
            with self.subTest(field=field, value=value):
                original = doc.get(field)
                doc[field] = value
                with self.assertRaises(ValueError): self.payments._verify('attempt')
                self.frappe.db.set_value.assert_not_called()
                doc[field] = original

    def test_existing_balance_checkout_prevents_double_allocation(self):
        self.frappe.db.exists.return_value = True
        with self.assertRaises(ValueError): self.payments._verify('attempt')
        self.frappe.db.set_value.assert_not_called()

    def test_pending_or_failed_full_checkout_never_settles_either_instalment(self):
        self.attempt.amount = 1
        self.data['payment_method'] = 'Visa'
        for code, state in [(0, 'Pending'), (2, 'Failed')]:
            self.data['status_code'] = code
            self.assertEqual(self.payments._verify('attempt'), state)
            self.assertEqual(self.attempt.status, state)
            self.assertIsNone(self.attempt.balance_payment)
            self.assertEqual(self.deposit.status, 'Unpaid')
            self.assertEqual(self.balance.status, 'Unpaid')
        self.queue.assert_not_called()

    def test_new_whole_shilling_order_also_settles_both_for_card_payment(self):
        self.attempt.amount = 1
        self.data['payment_method'] = 'Visa'
        self.assertEqual(self.payments._verify('attempt'), 'Paid')
        self.assertEqual(self.balance.status, 'Paid')

    def test_reversed_obligation_with_unreversed_prior_attempt_stays_blocked(self):
        self.deposit.update(status='Reversed', paid_attempt='earlier')
        self.frappe.db.get_value.return_value = 'Paid'
        with self.assertRaises(ValueError):
            self.payments._verify('attempt')
        self.frappe.db.set_value.assert_not_called()

    def test_reversed_full_payment_can_be_retried_with_a_new_verified_attempt(self):
        self.payments._verify('attempt')
        self.data['status_code'] = 3
        self.payments._verify('attempt')
        self.assertEqual(self.payments._full_kes_checkout(
            self.deposit, self.quote, [self.deposit, self.balance]), 1)
        replacement = fixture.Record(name='replacement', payment='deposit', amount=1,
            currency='KES', tracking_id='tracking', merchant_reference='merchant',
            environment='live', status='Pending')
        replacement.reload = lambda: None
        self.docs['replacement'] = replacement
        self.frappe.db.get_value.return_value = 'Reversed'
        self.data.update(status_code=1, payment_method='Visa')
        self.assertEqual(self.payments._verify('replacement'), 'Paid')
        for target in (self.deposit, self.balance):
            self.assertEqual(target.paid_attempt, 'replacement')
        self.assertEqual(self.attempt.status, 'Reversed')

    def test_reversed_receipt_cannot_be_reinstated_by_stale_paid_response(self):
        self.payments._verify('attempt')
        self.data['status_code'] = 3
        self.payments._verify('attempt')
        self.data['status_code'] = 1
        self.assertEqual(self.payments._verify('attempt'), 'Reversed')
        self.assertEqual(self.balance.status, 'Reversed')

    def test_new_checkout_submits_one_shilling_without_increasing_instalment_amounts(self):
        self.payments._owned = MagicMock(return_value=fixture.Record(name='request'))
        self.payments._quote = MagicMock(return_value=self.quote)
        new_attempt = MagicMock()
        new_attempt.name, new_attempt.status = 'new', 'Creating'
        new_attempt.tracking_id = None
        original_get = self.frappe.get_doc.side_effect
        self.frappe.get_doc.side_effect = lambda dt, name=None: fixture.Record(insert=lambda **kw: new_attempt) if isinstance(dt, dict) else original_get(dt, name)
        self.frappe.db.get_value.return_value = None
        self.frappe.db.get_single_value.return_value = 'KES'
        self.payments._config = MagicMock(return_value=('live', 'https://test.example', 'key', 'secret', 'ipn', 'base'))
        self.payments._provider = MagicMock(side_effect=lambda path, body: dict(merchant_reference=body['id'], order_tracking_id='new-tracking', redirect_url='https://pay.pesapal.com/order'))
        self.frappe.db.set_value.side_effect = None
        self.payments.checkout('request', 'deposit', 'retry')
        self.assertEqual(self.payments._provider.call_args.args[1]['amount'], 1)
        self.assertEqual(self.deposit.amount, .5)
        self.assertEqual(self.balance.amount, .5)
        self.assertEqual(self.quote.total, 1)

    def test_billing_plan_only_offers_full_payment_when_rounding_exactly_covers_quote(self):
        self.assertEqual(self.payments._full_kes_checkout(self.deposit, self.quote, [self.deposit, self.balance]), 1)
        self.balance.amount = 1
        self.quote.total = 1.5
        self.assertIsNone(self.payments._full_kes_checkout(self.deposit, self.quote, [self.deposit, self.balance]))

    def test_receipts_validate_each_allocation_without_counting_the_whole_receipt_twice(self):
        self.payments._verify('attempt')
        path = Path(fixture.ROOT) / 'payment_receipts.py'
        spec = importlib.util.spec_from_file_location('allocation_receipts_tested', path)
        receipts = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(receipts)
        for payment in (self.deposit, self.balance):
            self.assertIs(receipts.verified_attempt(payment), self.attempt)
            self.assertEqual(receipts.receipt_context(payment, self.quote, self.attempt)['amount'], .5)
        self.attempt.balance_allocated = 1
        self.assertIsNone(receipts.verified_attempt(self.deposit))
        self.assertIsNone(receipts.verified_attempt(self.balance))

    def test_pure_rounding_rule_rejects_general_overpayment_and_partial_balance(self):
        for values in [(0.5, 0.5, 1, 2), (0.5, 1, 1.5, 1), (1, 1, 2, 2), (0, 1, 1, 1)]:
            self.assertFalse(fixture.rules.full_kes_settlement(*values))
        self.assertTrue(fixture.rules.full_kes_settlement(.5, .5, 1, 1))


if __name__ == '__main__': unittest.main()
