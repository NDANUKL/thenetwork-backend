"""Render the actual Jinja print format using fictional QA records.

Run with Jinja2 installed: python tools/preview_quotation.py --output /path/to/previews
Convert the resulting HTML using the target PDF renderer before deployment.
"""
import argparse
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]


class Document(SimpleNamespace):
    def get(self, key, default=None):
        return getattr(self, key, default)


def sample_quote(count=2, inclusive=False, legacy=False):
    items = [Document(project_title=f"Project {index + 1}: " + ["Land condition and occupancy check in Kirinyaga", "Shop condition and business activity check in Kajiado"][index % 2], description="Visit the agreed site, document visible conditions and provide photographs with a written verification report.", quantity=1, rate=10000.0, amount=10000.0, planned_scouts=1) for index in range(count)]
    subtotal = sum(item.amount for item in items)
    discount = subtotal * .1
    taxable = (subtotal - discount) / 1.16 if inclusive else subtotal - discount
    vat = taxable * .16
    total = round(taxable + vat, 2)
    return Document(name="DQ-2026-00320", request="DD-2026-00030", status="Issued", accepted_at=None, customer_name="Sample Customer", customer_email="customer@example.com", quotation_date="2026-10-21", valid_until="2026-11-04", currency="KES", items=items, subtotal=None if legacy else subtotal, discount_amount=discount, discount_type="Percentage", discount_value=10, tax_inclusive=inclusive, taxable_amount=round(taxable, 2), vat_rate=16, vat_amount=round(vat, 2), total=total, deposit_amount=round(total / 2, 2), balance_amount=round(total / 2, 2), agreed_completion_date="2026-11-08", terms="50% upfront; balance after report review. Scope changes require a revised quote.")


def render(quote):
    spec = importlib.util.spec_from_file_location("quotation_artwork", ROOT / "fieldpulse/quotation_pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    template = json.loads((ROOT / "fieldpulse/fieldpulse/print_format/diaspora_desk_quotation/diaspora_desk_quotation.json").read_text(encoding="utf-8"))["html"]
    frappe = SimpleNamespace(utils=SimpleNamespace(formatdate=lambda value: datetime.fromisoformat(str(value)).strftime("%d %b %Y")))
    body = Environment(undefined=StrictUndefined, autoescape=True).from_string(template).render(doc=quote, quotation_assets=module.quotation_assets(), frappe=frappe)
    return '<!doctype html><html><head><meta charset="utf-8"><style>@page{size:A4;margin:15mm}body{margin:0}</style></head><body><div class="print-format">' + body + '</div></body></html>'


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, quote in [("single", sample_quote(1)), ("multi", sample_quote()), ("long", sample_quote(12)), ("inclusive", sample_quote(inclusive=True)), ("legacy", sample_quote(legacy=True))]:
        (args.output / f"quotation-{name}.html").write_text(render(quote), encoding="utf-8")
