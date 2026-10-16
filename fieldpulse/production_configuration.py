"""Adopt the audited non-overlapping Diaspora Desk site configuration."""
import json
from pathlib import Path
import frappe

from fieldpulse.native_ownership import registry

NATIVE_EVENTS = set(registry()["server_scripts"])


def apply_configuration():
    payload = json.loads((Path(__file__).parent / "configuration" / "production-configuration.json").read_text(encoding="utf-8"))
    records = payload["records"]
    ownership = registry()

    priority = {"Role": 0, "DocType": 1, "Custom Field": 2, "Custom DocPerm": 3, "Property Setter": 4, "Server Script": 5, "Client Script": 6, "Print Format": 7}
    records.sort(key=lambda record: (priority[record["doctype"]], 0 if record.get("istable") else 1, record["name"]))
    originals = []
    for values in records:
        doctype, name = values["doctype"], values["name"]
        if doctype == "Server Script" and name in NATIVE_EVENTS:
            continue
        if doctype == "Client Script" and name in ownership["client_scripts"]:
            continue
        if doctype == "DocType" and name in ownership["doctypes"]:
            continue
        if doctype == "Print Format" and name == "Diaspora Desk Quotation":
            continue
        if doctype == "Custom Field":
            standard = frappe.get_doc("DocType", values["dt"])
            if any(field.fieldname == values["fieldname"] for field in standard.fields):
                continue
        if doctype == "Custom DocPerm":
            matched = frappe.db.get_value("Custom DocPerm", {"parent": values["parent"], "role": values["role"], "permlevel": values.get("permlevel", 0), "if_owner": values.get("if_owner", 0)}, "name")
            if matched:
                name = matched
        existing = frappe.db.exists(doctype, name)
        if existing:
            document = frappe.get_doc(doctype, name)
            originals.append(document.as_dict())
            updates = {key: value for key, value in values.items() if key not in {"doctype", "name"}}
            document.update(updates)
            document.save(ignore_permissions=True)
        else:
            frappe.get_doc(values).insert(ignore_permissions=True)
    if originals:
        frappe.get_doc({"doctype": "File", "file_name": "before-production-configuration-adoption.json", "is_private": 1, "content": frappe.as_json(originals)}).insert(ignore_permissions=True)
    frappe.clear_cache()
