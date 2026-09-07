"""Provision the initial Field Operations Coordinator account."""

import frappe

from fieldpulse.install import create_roles


COORDINATOR_EMAIL = "groundscout.recruit@gmail.com"
COORDINATOR_ROLE = "Field Operations Coordinator"


def execute():
    """Create or update Clarissa's least-privilege Desk account.

    No password is set and no email is sent from a migration. An administrator
    must complete the account invitation/password setup in Frappe Desk.
    """
    create_roles()

    if frappe.db.exists("User", COORDINATOR_EMAIL):
        user = frappe.get_doc("User", COORDINATOR_EMAIL)
        user.user_type = "System User"
        user.enabled = 1
        if not any(row.role == COORDINATOR_ROLE for row in user.roles):
            user.append("roles", {"role": COORDINATOR_ROLE})
        user.save(ignore_permissions=True)
    else:
        frappe.get_doc(
            {
                "doctype": "User",
                "email": COORDINATOR_EMAIL,
                "first_name": "Clarissa",
                "user_type": "System User",
                "send_welcome_email": 0,
                "roles": [{"role": COORDINATOR_ROLE}],
            }
        ).insert(ignore_permissions=True)

    frappe.db.commit()
