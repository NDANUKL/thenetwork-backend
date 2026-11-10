"""Reject new/backdated planning dates without rewriting elapsed historical plans."""
import frappe
from frappe.utils import getdate

FIELDS = {
    'DD Quotation': ('valid_until',),
    'DD Scout Offer': ('valid_until',),
    'Diaspora Request': ('deadline_date',),
    'Field Request': ('deadline',),
}


def validate(doc, method=None):
    previous = doc.get_doc_before_save()
    for field in FIELDS.get(doc.doctype, ()):
        value = doc.get(field)
        if not value or (previous and str(previous.get(field)) == str(value)):
            continue
        if getdate(value) < getdate():
            label = doc.meta.get_field(field).label
            frappe.throw(f'{label} must be today or later.')
