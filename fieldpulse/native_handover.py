"""Adopt native schemas and scripts only during an explicitly approved handover.

Never executed by the source migration tooling. Existing records and physical
columns stay intact. Frappe's normal migration backup is still required.
"""
import hashlib
import importlib
import json
from pathlib import Path
import frappe
from fieldpulse.native_ownership import registry


def require_approval():
    if not frappe.conf.get("dd_native_handover_approved"):
        frappe.throw("Production scripts remain authoritative. Explicit native handover approval is required before migration.")


def _backup(filename, originals):
    if originals:
        frappe.get_doc({"doctype": "File", "file_name": filename, "is_private": 1,
            "content": frappe.as_json(originals)}).insert(ignore_permissions=True)


def _digest(value):
    return hashlib.sha256(value.replace("\r\n", "\n").strip().encode()).hexdigest()


def preflight():
    require_approval()
    plan = registry()
    originals = []
    for name, spec in plan["server_scripts"].items():
        if spec["target"]:
            module, function = spec["target"].rsplit(".", 1)
            if not callable(getattr(importlib.import_module(module), function)):
                frappe.throw("Missing native handler for " + name)
        if not frappe.db.exists("Server Script", name):
            continue
        doc = frappe.get_doc("Server Script", name)
        if doc.script_type != spec["script_type"] or _digest(doc.script) != spec["sha256"]:
            frappe.throw("Production script changed since the parity audit: " + name + ". Re-audit before handover.")
        for key in ("api_method",) if spec["script_type"] == "API" else ("reference_doctype", "doctype_event") if spec["script_type"] == "DocType Event" else ():
            if doc.get(key) != spec.get(key):
                frappe.throw("Unexpected script target: " + name)
        originals.append(doc.as_dict())
    for name, spec in plan["client_scripts"].items():
        if not frappe.db.exists("Client Script", name):
            continue
        doc = frappe.get_doc("Client Script", name)
        if doc.dt != spec["doctype"] or _digest(doc.script) != spec["sha256"]:
            frappe.throw("Production client script changed since audit: " + name)
        originals.append(doc.as_dict())
    known = set(plan["server_scripts"])
    current = frappe.get_all("Server Script", filters={"name": ["like", "DD %"], "disabled": 0}, pluck="name")
    unknown = sorted(set(current) - known)
    if unknown:
        frappe.throw("Unaudited active DD scripts: " + ", ".join(unknown) + ". Re-audit before handover.")
    return originals


def adopt_schema():
    originals = preflight()
    root = Path(__file__).parent.parent
    schemas = {}
    for path in (root / "fieldpulse/fieldpulse/doctype").glob("*/*.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        schemas[schema["name"]] = schema
    custom_fields = []
    doctypes = []
    for dt, schema in schemas.items():
        if not frappe.db.exists("DocType", dt):
            continue
        # Validate all duplicate metadata before changing any of it.
        standard = {field["fieldname"]: field for field in schema["fields"]}
        for row in frappe.get_all("Custom Field", filters={"dt": dt}, fields=["name"]):
            document = frappe.get_doc("Custom Field", row.name)
            if document.fieldname in standard:
                if document.fieldtype != standard[document.fieldname]["fieldtype"]:
                    frappe.throw("Incompatible Custom Field " + document.name)
                custom_fields.append(document.as_dict())
        if dt in registry()["doctypes"]:
            document = frappe.get_doc("DocType", dt)
            for field in document.fields:
                expected = standard.get(field.fieldname)
                if not expected or field.fieldtype != expected["fieldtype"] or (field.get("options") or None) != (expected.get("options") or None):
                    frappe.throw("DD schema changed since audit: " + dt + "." + field.fieldname)
            doctypes.append(document.as_dict())
    _backup("before-native-dd-schema-adoption.json", {"scripts": originals, "doctypes": doctypes, "custom_fields": custom_fields})
    for document in doctypes:
        # Model sync will load the app's standard definition. No document rows are deleted.
        frappe.db.set_value("DocType", document["name"], {"custom": 0, "module": "FieldPulse"})
    for document in custom_fields:
        # Metadata only: NEVER call delete_doc, which could remove physical columns.
        frappe.db.delete("Custom Field", {"name": document["name"]})
    frappe.cache.delete_value("server_script_map")
    frappe.clear_cache()


def retire_scripts():
    originals = preflight()
    jobs = []
    for document in originals:
        if document["doctype"] == "Server Script" and document.get("script_type") == "Scheduler Event":
            for row in frappe.get_all("Scheduled Job Type", filters={"server_script": document["name"]}, fields=["name"]):
                jobs.append(frappe.get_doc("Scheduled Job Type", row.name).as_dict())
    _backup("before-native-dd-script-handover.json", {"scripts": originals, "scheduled_jobs": jobs})
    # Validate everything first, then change active states in the same transaction.
    for job in jobs:
        frappe.db.set_value("Scheduled Job Type", job["name"], "stopped", 1)
    for document in originals:
        dt = document["doctype"]
        frappe.db.set_value(dt, document["name"], "disabled" if dt == "Server Script" else "enabled", 1 if dt == "Server Script" else 0)
    frappe.cache.delete_value("server_script_map")
    frappe.clear_cache()
