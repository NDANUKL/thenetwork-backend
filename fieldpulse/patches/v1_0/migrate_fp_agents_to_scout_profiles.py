"""Create Scout Profiles from legacy FP Agents."""

import frappe


def execute():
    for agent in frappe.get_all("FP Agent", fields=["name", "user", "full_name", "phone"]):
        if frappe.db.exists("Scout Profile", {"legacy_fp_agent": agent.name}):
            continue

        profile = {
            "doctype": "Scout Profile",
            "scout_name": agent.full_name,
            "phone_number": agent.phone,
            "legacy_fp_agent": agent.name,
            # FP Agent has GPS/radius only; county requires manual backfill.
            "availability_status": "Available",
        }
        if agent.user:
            profile["user"] = agent.user

        frappe.get_doc(profile).insert(ignore_permissions=True)

    frappe.db.commit()
