"""Compatibility route for the simplified production assignment dialog."""
from fieldpulse.native_ownership import owned_api
import frappe

@frappe.whitelist(methods=["POST"])
@owned_api('DD Simplified Scout Assignment')
def assign(field_request, assignments):
    from fieldpulse.project_alignment import assign_project_scouts
    return assign_project_scouts(field_request, assignments)

@frappe.whitelist(methods=["POST"])
@owned_api('DD Assign Project Scouts')
def assign_project(field_request, assignments):
    from fieldpulse.project_alignment import assign_project_scouts
    return assign_project_scouts(field_request, assignments)
