"""Provider diagnostics are categorical; provider text must never reach logs."""
import unittest
from unittest.mock import Mock
import test_payments as fixture


class ProviderDiagnosticTests(unittest.TestCase):
    def setUp(self):
        fixture.FlowTests.setUp(self)

    def tearDown(self):
        fixture.FlowTests.tearDown(self)

    def test_diagnostic_redacts_payload_and_classifies_notification(self):
        error = self.payments.ProviderRejection({
            'status': '400', 'error': {'message': 'Invalid notification id SECRET'},
            'token': 'SECRET', 'redirect_url': 'https://private/SECRET'}, 200)
        self.assertEqual(str(error), 'Pesapal could not complete this action')
        self.assertEqual(error.diagnostic,
            'HTTP: 200\nProvider status: 400\nReason category: NOTIFICATION')
        self.assertNotIn('SECRET', repr(vars(error)))

    def test_billing_name_and_address_failures_are_classified_without_private_text(self):
        for message in ('First name is null or empty', 'Last name is required',
                        'Middle name is missing', 'Address line 1 contains special characters',
                        'Line 1 address is missing', 'Postal code is invalid'):
            with self.subTest(message=message):
                error = self.payments.ProviderRejection({
                    'status': '500', 'error': {'message': message + ' PRIVATE-CUSTOMER-DATA'}}, 200)
                self.assertIn('Reason category: BILLING_ADDRESS', error.diagnostic)
                self.assertNotIn('PRIVATE-CUSTOMER-DATA', repr(vars(error)))
                self.assertNotIn(message, repr(vars(error)))

    def test_unknown_or_malformed_payloads_are_not_serialized(self):
        for payload in (None, [], 'SECRET', {'status': 'SECRET', 'message': 'SECRET', 'error': 'SECRET'}):
            error = self.payments.ProviderRejection(payload, 'SECRET')
            self.assertEqual(error.diagnostic,
                'HTTP: unknown\nProvider status: unknown\nReason category: UNCLASSIFIED')
            self.assertNotIn('SECRET', repr(vars(error)))

    def provider_response(self, payload, status=200):
        self.payments._config = Mock(return_value=('sandbox', '', 'key', 'secret', '', 'https://provider'))
        self.frappe.cache.get_value.return_value = 'cached-token'
        response = Mock(status_code=status)
        response.json.return_value = payload
        self.payments.requests.request.return_value = response
        return response

    def test_json_rejection_keeps_safe_diagnostics(self):
        response = self.provider_response({'status': '400', 'message': 'Invalid currency SECRET'}, 400)
        with self.assertRaises(self.payments.ProviderRejection) as caught:
            self.payments._provider('/Transactions/SubmitOrderRequest', {'amount': .5})
        self.assertIn('Reason category: CURRENCY', caught.exception.diagnostic)
        self.assertNotIn('SECRET', repr(vars(caught.exception)))
        response.raise_for_status.assert_not_called()

    def test_success_and_http_authority_are_preserved(self):
        payload = {'status': '200', 'order_tracking_id': 'tracking'}
        response = self.provider_response(payload)
        self.assertEqual(self.payments._provider('/Transactions/SubmitOrderRequest', {'amount': .5}), payload)
        response.raise_for_status.assert_called_once()
        response.raise_for_status.side_effect = RuntimeError('HTTP failure')
        with self.assertRaisesRegex(RuntimeError, 'HTTP failure'):
            self.payments._provider('/Transactions/SubmitOrderRequest', {'amount': .5})

    def test_non_json_http_error_preserves_existing_http_handling(self):
        response = self.provider_response(None, 502)
        response.json.side_effect = ValueError('SECRET')
        response.raise_for_status.side_effect = RuntimeError('HTTP failure')
        with self.assertRaisesRegex(RuntimeError, 'HTTP failure'):
            self.payments._provider('/Transactions/SubmitOrderRequest', {'amount': .5})

    def test_http_failure_codes_remain_compatible(self):
        error = self.payments.ProviderRejection({'status': '400'}, 401)
        self.assertEqual(self.payments._reconciliation_failure_code(error), 'PROVIDER_HTTP_401')
        error = self.payments.ProviderRejection({'status': '400'}, 200)
        self.assertEqual(self.payments._reconciliation_failure_code(error), 'PROVIDER_REJECTED')
