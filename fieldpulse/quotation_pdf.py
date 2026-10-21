"""Self-contained quotation artwork for authenticated PDF downloads."""
import base64
import os
import sys
import tempfile
from functools import lru_cache
from contextlib import contextmanager
from xml.etree import ElementTree
from pathlib import Path


@lru_cache(maxsize=1)
def quotation_assets():
    public = Path(__file__).resolve().parent / "public"

    def data_uri(relative_path, mime):
        encoded = base64.b64encode((public / relative_path).read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    return {
        "logo": data_uri("images/DD_logo.png", "image/png"),
        "regular_woff": data_uri("fonts/quotation/Carlito-Regular.woff", "application/font-woff"),
        "bold_woff": data_uri("fonts/quotation/Carlito-Bold.woff", "application/font-woff"),
        "regular": data_uri("fonts/quotation/Carlito-Regular.ttf", "font/ttf"),
        "bold": data_uri("fonts/quotation/Carlito-Bold.ttf", "font/ttf"),
    }


@contextmanager
def quotation_font_environment():
    """Give this PDF subprocess its own Fontconfig without changing the worker."""
    environment = os.environ.copy()
    if not sys.platform.startswith("linux"):
        yield environment
        return
    font_dir = Path(__file__).resolve().parent / "public/fonts/quotation"
    with tempfile.TemporaryDirectory(prefix="dd-quotation-fonts-") as temporary:
        root = ElementTree.Element("fontconfig")
        ElementTree.SubElement(root, "dir").text = str(font_dir)
        ElementTree.SubElement(root, "cachedir").text = str(Path(temporary) / "cache")
        alias = ElementTree.SubElement(root, "alias")
        ElementTree.SubElement(alias, "family").text = "sans-serif"
        prefer = ElementTree.SubElement(alias, "prefer")
        ElementTree.SubElement(prefer, "family").text = "Carlito"
        config = Path(temporary) / "fonts.conf"
        ElementTree.ElementTree(root).write(config, encoding="utf-8", xml_declaration=True)
        environment["FONTCONFIG_FILE"] = str(config)
        yield environment


def render_quotation_pdf(html):
    """Preserve Frappe PDF preparation/security with per-render font settings."""
    import pdfkit
    from frappe.utils.pdf import prepare_options, cleanup

    html, options = prepare_options(html, {
        "page-size": "A4", "margin-top": "15mm", "margin-bottom": "15mm",
        "margin-left": "15mm", "margin-right": "15mm",
    })
    options.update({
        "disable-javascript": "", "disable-local-file-access": "",
        "disable-smart-shrinking": "",
    })
    try:
        with quotation_font_environment() as environment:
            configuration = pdfkit.configuration(environ=environment)
            return pdfkit.from_string(html, False, options=options, configuration=configuration)
    finally:
        cleanup(options)
