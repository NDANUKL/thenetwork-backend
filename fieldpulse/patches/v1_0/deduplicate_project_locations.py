"""Reload the corrected location table metadata without altering site records."""
import frappe


def execute():
    # Normal model sync adopts the corrected JSON. Force reload also covers sites
    # whose old metadata cache or imported modified timestamp skipped that sync.
    frappe.reload_doc("fieldpulse", "doctype", "field_request", force=True)
    meta = frappe.get_meta("Field Request", cached=False)
    fields = [field for field in meta.fields if field.fieldname == "project_locations"]
    if (len(fields) != 1 or fields[0].fieldtype != "Table"
            or fields[0].options != "DD Request Site"):
        frappe.throw("Field Request must have exactly one project_locations table pointing to DD Request Site")
    frappe.clear_cache(doctype="Field Request")
