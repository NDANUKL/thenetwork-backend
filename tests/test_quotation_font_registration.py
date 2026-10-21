"""Linux font registration must precede quotation rendering."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quotation_font_registration", ROOT / "fieldpulse/quotation_pdf.py")
fonts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fonts)


class FontRegistrationTests(unittest.TestCase):
    def tearDown(self):
        fonts.ensure_quotation_fonts.cache_clear()

    def test_linux_registers_bundled_fonts_and_checks_both_weights_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            target = data / "fonts/fieldpulse-quotation"

            def run(command, **kwargs):
                if command[0] == "fc-cache":
                    return subprocess.CompletedProcess(command, 0)
                weight = command[-1].split("style=")[1]
                return subprocess.CompletedProcess(command, 0, str(target / f"Carlito-{weight}.ttf"))

            with patch.object(fonts.sys, "platform", "linux"), patch.dict(fonts.os.environ, {"XDG_DATA_HOME": str(data)}), patch.object(fonts.subprocess, "run", side_effect=run) as process:
                fonts.ensure_quotation_fonts()
                fonts.ensure_quotation_fonts()
                self.assertEqual(process.call_count, 3)
                for weight in ("Regular", "Bold"):
                    self.assertEqual((target / f"Carlito-{weight}.ttf").read_bytes(), (ROOT / f"fieldpulse/public/fonts/quotation/Carlito-{weight}.ttf").read_bytes())

    def test_font_substitution_fails_instead_of_silently_downloading_wrong_font(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(fonts.sys, "platform", "linux"), patch.dict(fonts.os.environ, {"XDG_DATA_HOME": temporary}), patch.object(fonts.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "/system/NimbusSans.ttf")):
                with self.assertRaisesRegex(RuntimeError, "substituted Carlito"):
                    fonts.ensure_quotation_fonts()

    def test_non_linux_uses_embedded_font_sources_without_fontconfig(self):
        with patch.object(fonts.sys, "platform", "win32"), patch.object(fonts.subprocess, "run") as process:
            fonts.ensure_quotation_fonts()
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
