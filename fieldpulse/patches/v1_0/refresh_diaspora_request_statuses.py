"""Recalculate request status across all planned projects after schema sync."""
import frappe


def execute():
    from fieldpulse.project_alignment import sync_request_status
    for name in frappe.get_all("Diaspora Request", pluck="name"):
        sync_request_status(frappe.get_doc("Diaspora Request", name))
