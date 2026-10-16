"""Remove duplicate Custom Field metadata before native identity model sync."""
import frappe

def execute():
    originals = []
    for name in ["Field Request-project_id", "Diaspora Request-project_contract_version"]:
        if frappe.db.exists("Custom Field", name):
            originals.append(frappe.get_doc("Custom Field", name).as_dict())
    if originals:
        frappe.get_doc({"doctype": "File", "file_name": "before-native-project-identity-fields.json", "is_private": 1, "content": frappe.as_json(originals)}).insert(ignore_permissions=True)
    for original in originals:
        # Keep physical columns and their data; native fields adopt them on sync.
        frappe.db.delete("Custom Field", {"name": original["name"]})
    frappe.clear_cache()
