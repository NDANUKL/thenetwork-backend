"""Verify the fonts in an actual downloaded quotation (requires pypdf)."""
import argparse
from pathlib import Path
from pypdf import PdfReader


def verify(path):
    reader = PdfReader(path)
    names = set()
    for page in reader.pages:
        resources = page.get("/Resources", {}).get_object()
        for font in resources.get("/Font", {}).get_object().values():
            names.add(str(font.get_object().get("/BaseFont", "")))
    if not names or any("carlito" not in name.lower() for name in names):
        raise ValueError(f"Quotation contains missing or substituted fonts: {sorted(names)}")
    if not any("bold" in name.lower() for name in names):
        raise ValueError("Carlito Bold was not embedded")
    if not any("bold" not in name.lower() for name in names):
        raise ValueError("Carlito Regular was not embedded")
    text = " ".join((page.extract_text() or "") for page in reader.pages)
    if "QUOTATION" not in text or "Total payable" not in text:
        raise ValueError("Quotation text is not extractable")
    return sorted(names)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    print("Verified quotation fonts:", ", ".join(verify(args.pdf)))
