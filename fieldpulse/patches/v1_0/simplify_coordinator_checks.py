"""Preserve existing location verification when replacing the dropdown."""
import frappe


def execute():
    frappe.db.sql("UPDATE `tabDD Request Site` SET location_verified = CASE WHEN confirmation_status = 'Confirmed for dispatch' THEN 1 ELSE 0 END")
