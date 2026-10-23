"""Print-template regressions independent of a live Frappe site."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quotation_preview", ROOT / "tools/preview_quotation.py")
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


class QuotationPrintTests(unittest.TestCase):
    def test_branding_and_no_signature_section(self):
        html = preview.render(preview.sample_quote())
        self.assertIn("data:image/png;base64,", html)
        self.assertEqual(html.count("data:font/ttf;base64,"), 2)
        self.assertEqual(html.count("data:application/font-woff;base64,"), 2)
        self.assertNotIn("DDCarlito", html)
        self.assertIn("font-family:Carlito", html)
        self.assertLess(html.index("format('woff')"), html.index("format('truetype')"))
        self.assertIn("KES 20,880.00", html)
        self.assertIn("KES 10,440.00", html)
        self.assertNotIn("Signature", html)
        self.assertNotIn("PLEASE CONFIRM YOUR ACCEPTANCE", html)

    def test_compact_two_column_layout_and_metadata(self):
        html = preview.render(preview.sample_quote())
        self.assertIn('class="dd-customer"', html)
        self.assertIn('.dd-customer{text-align:right;}', html)
        self.assertIn('Project Description</th>', html)
        self.assertNotIn('Quantity / Rate', html)
        self.assertNotIn('dd-quantity', html)
        self.assertNotIn('PROJECT DESCRIPTION', html)
        self.assertLess(html.index('Quotation No.</td>'), html.index('Request reference</td>'))
        self.assertLess(html.index('Request reference</td>'), html.index('Issue date</td>'))
        self.assertNotIn('Scout assignment begins', html)

    def test_vat_inclusive_and_legacy_breakdowns(self):
        inclusive = preview.render(preview.sample_quote(inclusive=True))
        self.assertIn("Subtotal (VAT inclusive)", inclusive)
        self.assertIn("Net before VAT", inclusive)
        self.assertIn("KES 18,000.00", inclusive)
        legacy = preview.render(preview.sample_quote(legacy=True))
        self.assertNotIn("Net before VAT", legacy)
        self.assertNotIn("VAT (16%)", legacy)
        self.assertIn("KES 20,880.00", legacy)

    def test_fixed_discount_prints_percentage_and_amount(self):
        quote = preview.sample_quote()
        quote.discount_type = 'Fixed amount'
        quote.discount_value = quote.discount_amount
        html = preview.render(quote)
        self.assertIn('Discount (10.00%)', html)
        self.assertIn('-KES 2,000.00', html)

    def test_customer_and_scope_content_is_escaped(self):
        quote = preview.sample_quote()
        quote.customer_name = '<script>alert("name")</script>'
        quote.items[0].description = '<img src=x onerror="alert(1)">'
        html = preview.render(quote)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
