import frappe

def execute():
    active = frappe.get_all("Server Script", filters={"name": ["in", ["DD Field Project Mapping", "DD Field Project Expansion", "DD Quotation Validation", "DD Payment Deposit Gate"]], "disabled": 0}, pluck="name")
    if active and not frappe.conf.get("dd_native_handover_approved"):
        frappe.throw("Production scripts remain authoritative. Obtain the owner's explicit native-handover approval before deploying retirement migrations.")
