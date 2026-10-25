"""Idempotent role creation only; never assigns people or enables money actions."""
def install():
    import frappe
    if not frappe.db.exists('Role','Finance'):
        frappe.get_doc(dict(doctype='Role',role_name='Finance',desk_access=1)).insert(ignore_permissions=True)
