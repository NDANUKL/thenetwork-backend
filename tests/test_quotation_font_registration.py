"""PDF rendering uses isolated fonts without installing or rejecting system fonts."""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quotation_pdf_isolated", ROOT / "fieldpulse/quotation_pdf.py")
fonts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fonts)


class FontEnvironmentTests(unittest.TestCase):
    def test_linux_uses_bundled_fonts_and_leaves_global_environment_unchanged(self):
        original = os.environ.get("FONTCONFIG_FILE")
        with patch.object(fonts.sys, "platform", "linux"):
            with fonts.quotation_font_environment() as environment:
                config = Path(environment["FONTCONFIG_FILE"])
                self.assertTrue(config.exists())
                root = ElementTree.parse(config).getroot()
                self.assertEqual(Path(root.findtext("dir")).resolve(), (ROOT / "fieldpulse/public/fonts/quotation").resolve())
                self.assertEqual(root.findtext("alias/prefer/family"), "Carlito")
                self.assertEqual(os.environ.get("FONTCONFIG_FILE"), original)
            self.assertFalse(config.exists())

    def test_non_linux_does_not_require_fontconfig_tools(self):
        with patch.object(fonts.sys, "platform", "win32"):
            with fonts.quotation_font_environment() as environment:
                self.assertEqual(environment, dict(os.environ))
                self.assertIsNot(environment, os.environ)

    def test_pdf_renderer_keeps_frappe_preparation_and_security_options(self):
        pdfkit = MagicMock()
        pdfkit.from_string.return_value = b"%PDF-verified"
        frappe_pdf = types.ModuleType("frappe.utils.pdf")
        frappe_pdf.prepare_options = MagicMock(return_value=("<html>prepared</html>", {"page-size": "A4"}))
        frappe_pdf.cleanup = MagicMock()
        with patch.dict(sys.modules, {"pdfkit": pdfkit, "frappe.utils.pdf": frappe_pdf}), patch.object(fonts.sys, "platform", "linux"):
            def configuration(**kwargs):
                self.assertTrue(Path(kwargs["environ"]["FONTCONFIG_FILE"]).exists())
                return "isolated-configuration"
            pdfkit.configuration.side_effect = configuration
            self.assertEqual(fonts.render_quotation_pdf("<html>quote</html>"), b"%PDF-verified")
        options = pdfkit.from_string.call_args.kwargs["options"]
        self.assertIn("disable-javascript", options)
        self.assertIn("disable-local-file-access", options)
        self.assertEqual(pdfkit.from_string.call_args.kwargs["configuration"], "isolated-configuration")
        frappe_pdf.prepare_options.assert_called_once()
        frappe_pdf.cleanup.assert_called_once_with(options)

    def test_cleanup_runs_after_renderer_failure(self):
        pdfkit = MagicMock()
        pdfkit.from_string.side_effect = OSError("Renderer failed")
        frappe_pdf = types.ModuleType("frappe.utils.pdf")
        frappe_pdf.prepare_options = MagicMock(return_value=("<html/>", {}))
        frappe_pdf.cleanup = MagicMock()
        with patch.dict(sys.modules, {"pdfkit": pdfkit, "frappe.utils.pdf": frappe_pdf}):
            with self.assertRaisesRegex(OSError, "Renderer failed"):
                fonts.render_quotation_pdf("<html/>")
        frappe_pdf.cleanup.assert_called_once()


if __name__ == "__main__":
    unittest.main()
