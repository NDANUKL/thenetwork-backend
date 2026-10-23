import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from tests.test_native_integration import load, fake_frappe


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.api = fake_frappe()
        self.api.DoesNotExistError = LookupError
        self.module = load('payment_receipts_test', 'fieldpulse/payment_receipts.py', {'frappe': self.api})
        self.payment = Record(name='PAY-1', request='DD-1', quotation='DQ-1', kind='deposit', amount=50,
            currency='USD', status='Paid', paid_attempt='ATT-1', paid_at='2026-10-23')
        self.attempt = Record(payment='PAY-1', status='Paid', amount=50, currency='USD',
            confirmation_code='CONF-1', verified_at='2026-10-23', environment='live')
        self.api.get_doc.return_value = self.attempt

    def test_only_verified_matching_payments_get_receipts(self):
        document = self.module.receipt_document(self.payment, 'DD-1')
        self.assertEqual(document['kind'], 'receipt')
        self.assertEqual(document['download_url'], '/api/customer/requests/DD-1/receipts/PAY-1')
        for key, value in [('payment','OTHER'), ('status','Pending'), ('amount',49), ('currency','KES'), ('confirmation_code',''), ('verified_at',None)]:
            with self.subTest(key=key):
                old = self.attempt[key]
                self.attempt[key] = value
                self.assertIsNone(self.module.receipt_document(self.payment, 'DD-1'))
                self.attempt[key] = old

    def test_unpaid_reversed_or_unowned_payments_have_no_receipt(self):
        for status in ('Unpaid','Reversed'):
            self.payment.status = status
            self.assertIsNone(self.module.receipt_document(self.payment, 'DD-1'))
        self.payment.status = 'Paid'
        self.assertIsNone(self.module.receipt_document(self.payment, 'OTHER'))

    def test_download_checks_request_ownership_before_lookup(self):
        owned = MagicMock(side_effect=PermissionError('Not yours'))
        with patch.dict(sys.modules, {'fieldpulse.payments': types.SimpleNamespace(_owned=owned)}):
            with self.assertRaises(PermissionError): self.module.download_receipt('DD-OTHER','PAY-1')
        self.api.get_doc.assert_not_called()

    def test_download_rejects_payment_from_another_request(self):
        self.api.db.exists.return_value = None
        with patch.dict(sys.modules, {'fieldpulse.payments': types.SimpleNamespace(_owned=lambda reference: Record(name=reference))}):
            with self.assertRaises(LookupError): self.module.download_receipt('DD-1','OTHER')
        self.api.get_doc.assert_not_called()

    def test_download_renders_only_verified_owned_payment(self):
        quote = Record(request='DD-1',customer_name='Client',customer_email='client@example.com',items=[Record(project_title='Land check')])
        self.api.db.exists.return_value = 'PAY-1'
        self.api.get_doc.side_effect = lambda dt,name: {'DD Payment':self.payment,'DD Payment Attempt':self.attempt,'DD Quotation':quote}[dt]
        self.api.render_template.return_value = '<p>Receipt</p>'
        with patch.dict(sys.modules, {'fieldpulse.payments':types.SimpleNamespace(_owned=lambda reference:Record(name=reference))}), patch('fieldpulse.quotation_pdf.render_quotation_pdf',return_value=b'%PDF-receipt'):
            self.module.download_receipt('DD-1','PAY-1')
        self.assertEqual(self.api.response['filename'],'RCP-PAY-1.pdf')
        self.assertEqual(self.api.response['filecontent'],b'%PDF-receipt')
        self.assertEqual(self.api.render_template.call_args.args[1]['receipt']['confirmation'],'CONF-1')

    def test_receipt_context_preserves_currency_and_labels_test_payments(self):
        quote = Record(customer_name='Client', customer_email='client@example.com')
        quote.items = [Record(project_title='Land check')]
        self.attempt.environment = 'sandbox'
        context = self.module.receipt_context(self.payment, quote, self.attempt)
        self.assertTrue(context['test_payment'])
        self.assertEqual(context['currency'], 'USD')
        self.assertEqual(context['amount'],50)
        self.assertEqual(context['payment_label'],'50% deposit')

    def test_receipt_template_escapes_customer_data_and_formats_amounts(self):
        from jinja2 import Environment, StrictUndefined
        template = (Path(__file__).parents[1]/'fieldpulse/templates/payment_receipt.html').read_text(encoding='utf-8')
        receipt = dict(receipt_number='RCP-1', reference='DD-1', quotation='DQ-1', customer_name='<script>bad</script>', customer_email='client@example.com', paid_at='2026-10-23', currency='USD', amount=50, payment_label='50% deposit', confirmation='CONF-1', test_payment=False, projects=['Land check'])
        html=Environment(undefined=StrictUndefined,autoescape=True).from_string(template).render(receipt=receipt,quotation_assets=dict(regular_woff='',regular='',bold_woff='',bold='',logo=''),frappe=types.SimpleNamespace(utils=types.SimpleNamespace(formatdate=lambda value:value)))
        self.assertIn('USD 50.00',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertNotIn('<script>',html)
        self.assertIn('Amount received',html)
