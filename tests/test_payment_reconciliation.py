"""Retry scheduling and logging must not change financial verification authority."""
import unittest
import types
from datetime import datetime, timedelta
from unittest.mock import Mock
import test_payments as fixture


class RetryTests(unittest.TestCase):
    def setUp(self):
        fixture.FlowTests.setUp(self)
        self.now = datetime(2026, 10, 30, 12)
        self.payments.now_datetime = lambda: self.now
        self.settings = fixture.Record(enabled=1, environment='sandbox')
        self.frappe.get_doc.return_value = self.settings
        self.row = fixture.Record(name='synthetic-attempt', status='Pending', tracking_id='synthetic', environment='sandbox', reconcile_failures=0, reconcile_error_code=None, next_reconcile_at=None)
        self.frappe.cache.make_key.return_value = b'synthetic-site|dd:pesapal:reconcile'
        self.frappe.cache.lock.return_value.acquire.return_value = True
        self.payments._verify = Mock()
        class Timeout(Exception): pass
        class ConnectionError(Exception): pass
        class HTTPError(Exception): pass
        self.errors = types.SimpleNamespace(Timeout=Timeout, ConnectionError=ConnectionError, HTTPError=HTTPError)
        self.payments.requests = types.SimpleNamespace(exceptions=self.errors)
        self.writes=[]
        def set_value(doctype, name, values):
            self.writes.append(values)
            self.row.update(values)
        self.frappe.db.set_value.side_effect=set_value
        def rows(doctype, **query):
            self.assertEqual(query['filters']['environment'], 'sandbox')
            self.assertEqual(query['filters']['status'], ['in', ['Pending', 'Review']])
            self.assertEqual(query['filters']['tracking_id'], ['is', 'set'])
            self.assertEqual(query['or_filters'], [['next_reconcile_at', 'is', 'not set'], ['next_reconcile_at', '<=', self.now]])
            return [fixture.Record(self.row)] if not self.row.next_reconcile_at or self.row.next_reconcile_at <= self.now else []
        self.frappe.get_all.side_effect=rows

    def tearDown(self):
        fixture.FlowTests.tearDown(self)

    def test_failed_attempt_waits_and_logs_only_once_for_same_reason(self):
        self.payments._verify.side_effect=self.errors.Timeout('private provider token and body')
        self.payments.reconcile()
        self.assertEqual(self.row.reconcile_failures, 1)
        self.assertEqual(self.row.next_reconcile_at, self.now+timedelta(minutes=15))
        self.assertEqual(self.row.status, 'Pending')
        self.payments.reconcile()
        self.payments._verify.assert_called_once()
        self.now += timedelta(minutes=15)
        self.payments.reconcile()
        self.assertEqual(self.row.reconcile_failures, 2)
        self.assertEqual(self.row.next_reconcile_at, self.now+timedelta(minutes=30))
        self.frappe.log_error.assert_called_once()
        logged=self.frappe.log_error.call_args.kwargs
        self.assertIn('PROVIDER_TIMEOUT', logged['message'])
        self.assertNotIn('private', logged['message'])
        self.assertTrue(logged['defer_insert'])
        self.assertEqual(logged['reference_name'], self.row.name)
        for values in self.writes:
            self.assertTrue(set(values) <= {'reconcile_failures','next_reconcile_at','reconcile_error_code','reconcile_failed_at'})
        self.assertEqual(self.frappe.db.rollback.call_count, 2)

    def test_backoff_caps_at_one_day_and_recovery_resets_metadata(self):
        self.row.update(reconcile_failures=100, reconcile_error_code='PROVIDER_TIMEOUT')
        self.payments._verify.side_effect=self.errors.Timeout('private')
        self.payments.reconcile()
        self.assertEqual(self.row.next_reconcile_at, self.now+timedelta(days=1))
        self.now+=timedelta(days=1)
        self.payments._verify.side_effect=None
        self.payments.reconcile()
        self.assertEqual(self.row.reconcile_failures, 0)
        self.assertIsNone(self.row.next_reconcile_at)
        self.assertIsNone(self.row.reconcile_error_code)

    def test_changed_failure_code_emits_new_log(self):
        self.row.update(reconcile_failures=2, reconcile_error_code='PROVIDER_TIMEOUT')
        self.payments._verify.side_effect=ValueError('Payment reference mismatch')
        self.payments.reconcile()
        self.assertEqual(self.row.reconcile_error_code,'REFERENCE_MISMATCH')
        self.frappe.log_error.assert_called_once()

    def test_disabled_settings_and_overlapping_job_do_no_work(self):
        self.settings.enabled=0
        self.payments.reconcile()
        self.frappe.get_all.assert_not_called()
        self.payments._verify.assert_not_called()
        self.frappe.log_error.assert_not_called()
        self.frappe.cache.lock.return_value.release.assert_called_once()
        self.frappe.cache.lock.assert_called_with(b'synthetic-site|dd:pesapal:reconcile', timeout=7200)
        self.settings.enabled=1
        self.frappe.cache.lock.return_value.acquire.return_value=False
        self.payments.reconcile()
        self.frappe.get_all.assert_not_called()

    def test_safe_provider_codes_never_include_response_body(self):
        error=self.errors.HTTPError('private url token')
        error.response=types.SimpleNamespace(status_code=401)
        self.assertEqual(self.payments._reconciliation_failure_code(error),'PROVIDER_HTTP_401')
        self.assertEqual(self.payments._reconciliation_failure_code(RuntimeError('private')),'VERIFICATION_FAILED')
