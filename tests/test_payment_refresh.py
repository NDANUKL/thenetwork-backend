"""Interactive refresh checks one owned transaction; scheduled recovery is separate."""
import unittest
import sys
import types
from unittest.mock import Mock, patch
import test_payments as fixture


class RefreshTests(unittest.TestCase):
    def setUp(self):
        fixture.FlowTests.setUp(self)
        self.payments._owned = Mock()
        self.payments._config = Mock(return_value=('live',))
        self.payments._verify = Mock(return_value='Paid')
        self.frappe.db.sql.return_value = [fixture.Record(name='latest', status='Pending', tracking_id='tracking')]

    def tearDown(self):
        fixture.FlowTests.tearDown(self)

    def test_only_latest_owned_attempt_is_checked_directly(self):
        self.frappe.db.sql.return_value.append(fixture.Record(name='older', status='Pending', tracking_id='old'))
        result = self.payments.refresh('owned-request')
        self.payments._owned.assert_called_once_with('owned-request')
        self.payments._verify.assert_called_once_with('latest', interactive=True)
        query = self.frappe.db.sql.call_args
        self.assertIn('LIMIT 1', query.args[0])
        self.assertIn('ORDER BY a.creation DESC', query.args[0])
        self.assertEqual(query.args[1], ['owned-request', 'live'])
        self.assertEqual(result, {'success': True, 'pending': False, 'status': 'Paid'})
        self.frappe.enqueue.assert_not_called()

    def test_explicit_payment_is_scoped_to_the_owned_request(self):
        self.frappe.db.exists.return_value = True
        self.payments.refresh('owned-request', 'owned-payment')
        self.frappe.db.exists.assert_called_once_with('DD Payment', {'name': 'owned-payment', 'request': 'owned-request'})
        self.assertEqual(self.frappe.db.sql.call_args.args[1], ['owned-request', 'live', 'owned-payment'])

    def test_foreign_requests_and_payments_do_no_provider_work(self):
        self.payments._owned.side_effect = PermissionError
        with self.assertRaises(PermissionError): self.payments.refresh('foreign')
        self.payments._verify.assert_not_called()
        self.frappe.db.sql.assert_not_called()
        self.payments._owned.side_effect = None
        self.frappe.db.exists.return_value = False
        with self.assertRaises(ValueError): self.payments.refresh('owned-request', 'foreign-payment')
        self.payments._verify.assert_not_called()

    def test_provider_failure_preserves_uncertainty_without_mutating_payment(self):
        self.payments._verify.side_effect = TimeoutError('private provider data')
        self.assertEqual(self.payments.refresh('owned-request'), {'success': True, 'pending': True})
        self.frappe.db.rollback.assert_called_once()
        self.frappe.db.set_value.assert_not_called()
        self.frappe.enqueue.assert_not_called()

    def test_missing_tracking_id_remains_pending_without_retrying_an_order(self):
        self.frappe.db.sql.return_value = [fixture.Record(name='creating', status='Creating', tracking_id=None)]
        self.assertEqual(self.payments.refresh('owned-request'), {'success': True, 'pending': True})
        self.payments._verify.assert_not_called()

    def test_no_attempt_or_terminal_attempt_needs_no_provider_call(self):
        self.frappe.db.sql.return_value = []
        self.assertFalse(self.payments.refresh('owned-request')['pending'])
        for state in ('Paid', 'Failed', 'Reversed'):
            self.frappe.db.sql.return_value = [fixture.Record(name='terminal', status=state, tracking_id='tracking')]
            self.assertFalse(self.payments.refresh('owned-request')['pending'])
        self.payments._verify.assert_not_called()

    def test_unconfirmed_provider_response_keeps_retry_guard(self):
        self.payments._verify.return_value = 'Pending'
        self.assertTrue(self.payments.refresh('owned-request')['pending'])

    def test_billing_marks_outstanding_attempts_pending_but_not_paid_obligations(self):
        quote = types.SimpleNamespace(name='Q', items=[], status='Accepted', currency='USD', total=100,
            valid_until='2099-01-01', get=lambda key: None)
        payment = fixture.Record(name='P', kind='deposit', amount=50, status='Unpaid')
        self.payments._quote = Mock(return_value=quote)
        self.payments._obligations = Mock(return_value=[payment])
        self.frappe.db.exists.return_value = True
        with patch.dict(sys.modules, {'fieldpulse.payment_receipts': types.SimpleNamespace(receipt_document=lambda *args: None)}):
            result = self.payments._billing(fixture.Record(name='request'))
            self.assertTrue(payment.pending_confirmation)
            self.assertFalse(payment.can_pay)
            self.assertNotIn('refresh_pending', result)
            payment.status = 'Paid'
            self.payments._billing(fixture.Record(name='request'))
            self.assertFalse(payment.pending_confirmation)


class ProviderBudgetTests(unittest.TestCase):
    def setUp(self): fixture.FlowTests.setUp(self)
    def tearDown(self): fixture.FlowTests.tearDown(self)

    def test_interactive_status_uses_short_timeouts(self):
        self.payments._config = Mock(return_value=('live', 'origin', 'key', 'secret', 'ipn', 'https://provider'))
        self.frappe.cache.get_value.return_value = 'cached-token'
        self.payments.requests.request.return_value.status_code = 200
        self.payments.requests.request.return_value.json.return_value = {'status': '200'}
        self.payments._provider('/Transactions/GetTransactionStatus', interactive=True)
        self.assertEqual(self.payments.requests.request.call_args.kwargs['timeout'], (3, 10))
        self.payments._provider('/Transactions/GetTransactionStatus')
        self.assertEqual(self.payments.requests.request.call_args.kwargs['timeout'], 25)
        self.frappe.cache.get_value.return_value = None
        self.payments.requests.post.return_value.json.return_value = {'status': '200', 'token': 'test-token', 'expiryDate': '2099-01-01T00:00:00Z'}
        self.payments._provider('/Transactions/GetTransactionStatus', interactive=True)
        self.assertEqual(self.payments.requests.post.call_args.kwargs['timeout'], (3, 7))
