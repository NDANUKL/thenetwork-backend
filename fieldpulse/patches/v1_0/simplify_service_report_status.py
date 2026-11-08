"""Keep unpublished reports private when retiring the review status."""
import frappe


def execute():
    frappe.db.sql("""
        UPDATE `tabDD Service Report`
        SET status = 'Draft'
        WHERE status = 'Under review'
    """)
