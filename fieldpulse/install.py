import frappe

from fieldpulse.fieldpulse.constants import ROLES


def after_install():
    """Runs once when the app is installed onto a site."""
    create_roles()


def create_roles():
    for role_name in ROLES:
        if frappe.db.exists("Role", role_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 1,
            }
        ).insert(ignore_permissions=True)

    frappe.db.commit()
