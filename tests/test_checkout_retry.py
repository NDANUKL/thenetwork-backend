"""Regression coverage for retryable notification rejection and legacy recovery."""
import unittest
from unittest.mock import MagicMock
import test_payments as fixture


class CheckoutRetryTests(unittest.TestCase):
    def setUp(self): fixture.FlowTests.setUp(self)
    def tearDown(self): fixture.FlowTests.tearDown(self)

    def rejection(self, **extra):
        return self.payments.ProviderRejection(dict(status='500',
            error={'message': 'Invalid notification id'}, **extra), 200)

    def test_only_explicit_notification_rejection_without_order_allows_retry(self):
        self.assertTrue(self.rejection().order_rejected)
        for payload in ({'order_tracking_id': 'tracking'}, {'redirect_url': 'https://private'}):
            self.assertFalse(self.rejection(**payload).order_rejected)
        self.assertFalse(self.payments.ProviderRejection({'status': '500'}, 200).order_rejected)
        self.assertFalse(self.payments.ProviderRejection({'status': '500',
            'error': {'message': 'Invalid notification'}}, 502).order_rejected)

    def test_checkout_rejection_is_failed_not_review_and_preserves_unpaid_balance(self):
        self.payments._owned = MagicMock(return_value=fixture.Record(name='request'))
        self.payments._quote = MagicMock(return_value=fixture.Record(name='quote', status='Accepted'))
        obligation = fixture.Record(name='payment', request='request', quotation='quote',
            kind='deposit', status='Unpaid', currency='KES', amount=0.5)
        attempt = MagicMock()
        attempt.name, attempt.status = 'attempt', 'Creating'
        attempt.tracking_id, attempt.checkout_url = None, None
        self.frappe.get_doc.side_effect = [obligation, fixture.Record(insert=lambda **kwargs: attempt)]
        self.frappe.db.get_value.return_value = None
        self.frappe.db.get_single_value.return_value = 'KES'
        self.payments._config = MagicMock(return_value=('sandbox', 'https://test.example', 'key', 'secret', 'ipn', 'base'))
        self.payments._provider = MagicMock(side_effect=self.rejection())
        with self.assertRaisesRegex(ValueError, 'temporarily unavailable'):
            self.payments.checkout('request', 'payment', 'retry')
        values = self.frappe.db.set_value.call_args.args[2]
        self.assertEqual(values['status'], 'Failed')
        self.assertEqual(values['reconcile_error_code'], 'CHECKOUT_NOTIFICATION_REJECTED')
        self.assertEqual(obligation.status, 'Unpaid')
        self.assertEqual(self.frappe.db.commit.call_count, 2)

    def legacy(self):
        self.attempt = fixture.Record(name='legacy', status='Review', tracking_id=None,
            checkout_url=None, reconcile_error_code='PROVIDER_REJECTED')
        self.frappe.get_doc.return_value = self.attempt
        self.log = '\n'.join(['Payment attempt: legacy', 'Stage: provider_order',
            'Code: PROVIDER_REJECTED', 'HTTP: 200', 'Provider status: 500',
            'Reason category: NOTIFICATION'])
        self.frappe.get_all.return_value = [fixture.Record(error=self.log)]

    def test_exact_legacy_rejection_recovers_without_touching_payment(self):
        self.legacy()
        self.assertTrue(self.payments._recover_notification_rejection('legacy'))
        self.frappe.db.set_value.assert_called_once_with('DD Payment Attempt', 'legacy',
            {'status': 'Failed', 'reconcile_error_code': 'CHECKOUT_NOTIFICATION_REJECTED'})

    def test_legacy_unknown_or_partial_orders_never_unlock(self):
        for field, value in [('tracking_id', 'tracking'), ('checkout_url', 'https://private'),
                             ('status', 'Paid'), ('status', 'Creating'),
                             ('reconcile_error_code', 'PROVIDER_TIMEOUT')]:
            self.legacy()
            self.attempt[field] = value
            self.frappe.db.set_value.reset_mock()
            self.assertFalse(self.payments._recover_notification_rejection('legacy'))
            self.frappe.db.set_value.assert_not_called()
        for log in ('', self.log.replace('NOTIFICATION', 'UNCLASSIFIED'),
                    self.log.replace('provider_order', 'save_attempt')):
            self.legacy()
            self.frappe.get_all.return_value = [fixture.Record(error=log)]
            self.frappe.db.set_value.reset_mock()
            self.assertFalse(self.payments._recover_notification_rejection('legacy'))
            self.frappe.db.set_value.assert_not_called()

    def test_refresh_recovers_only_review_attempt_without_tracking(self):
        self.payments._owned = MagicMock()
        self.payments._config = MagicMock(return_value=('sandbox',))
        self.frappe.db.sql.return_value = [fixture.Record(name='legacy', status='Review', tracking_id=None)]
        self.legacy()
        self.assertEqual(self.payments.refresh('owned'), {'success': True, 'pending': False, 'status': 'Failed'})


if __name__ == '__main__': unittest.main()
