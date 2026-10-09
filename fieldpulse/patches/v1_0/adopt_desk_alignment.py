"""Retire only the Desk customizations now supplied by the app.

Custom Field rows are removed directly: physical columns and all data stay in
place for model sync. A private File retains the complete original definitions.
"""
import json
from pathlib import Path
import frappe

SERVER_SCRIPTS = {
    "DD Project Metadata": ("Diaspora Request", "Before Save"),
    "DD Field Project Mapping": ("Field Request", "Before Save"),
    "DD Field Project Expansion": ("Field Request", "After Save"),
    "DD Task Project Mapping": ("Field Task", "Before Save"),
    "DD Task Completion Rollup": ("Field Task", "After Save"),
    "DD Assign Project Scouts": (None, None),
}
CLIENT_SCRIPTS = {
    "DD Project Scout Assignment": "Field Request",
    "DD Request Scout Assignment": "Diaspora Request",
}
FIELDS = {
    "Diaspora Request": {"county", "project_details", "customer_target_date", "alignment_review"},
    "Diaspora Request Evidence": {"county", "project_number"},
    "Field Request": {"customer_target_date", "alignment_review", "project_number", "project_title",
                      "project_key", "deadline_preference", "evidence_requirements"},
    "Field Task": {"project_number", "project_title", "county", "request_type", "priority",
                   "task_brief", "evidence_requirements", "responsibility"},
}


def execute():
    originals = {"custom_fields": [], "server_scripts": [], "client_scripts": []}
    for name, (dt, event) in SERVER_SCRIPTS.items():
        if not frappe.db.exists("Server Script", name):
            continue
        doc = frappe.get_doc("Server Script", name)
        valid = (doc.script_type == "API" and doc.api_method == "dd_assign_project_scouts"
                 if dt is None else doc.script_type == "DocType Event"
                 and doc.reference_doctype == dt and doc.doctype_event == event)
        if not valid:
            frappe.throw("Unexpected definition for " + name + "; review before migrating.")
        originals["server_scripts"].append(doc.as_dict())
    for name, dt in CLIENT_SCRIPTS.items():
        if frappe.db.exists("Client Script", name):
            doc = frappe.get_doc("Client Script", name)
            if doc.dt != dt:
                frappe.throw("Unexpected definition for " + name + "; review before migrating.")
            originals["client_scripts"].append(doc.as_dict())
    schema_root = Path(__file__).parents[2] / "fieldpulse" / "doctype"
    for dt, names in FIELDS.items():
        folder = dt.lower().replace(" ", "_")
        schema = json.loads((schema_root / folder / (folder + ".json")).read_text(encoding="utf-8"))
        types = {row["fieldname"]: row["fieldtype"] for row in schema["fields"]}
        for row in frappe.get_all("Custom Field", filters={"dt": dt, "fieldname": ["in", list(names)]}, fields=["name"]):
            doc = frappe.get_doc("Custom Field", row.name)
            if doc.fieldtype != types[doc.fieldname]:
                frappe.throw("Incompatible Custom Field " + doc.name + "; review before migrating.")
            originals["custom_fields"].append(doc.as_dict())
    if frappe.db.exists("Custom HTML Block", "DD Field Operations Dashboard"):
        originals["dashboard"] = frappe.get_doc("Custom HTML Block", "DD Field Operations Dashboard").as_dict()
    if frappe.db.exists("Workspace", "Field Operations"):
        originals["workspace"] = frappe.get_doc("Workspace", "Field Operations").as_dict()
    if any(originals.values()):
        frappe.get_doc({"doctype": "File", "file_name": "desk-alignment-before-adoption.json",
                        "is_private": 1, "content": frappe.as_json(originals)}).insert(ignore_permissions=True)
    for doc in originals["server_scripts"]:
        frappe.db.set_value("Server Script", doc["name"], "disabled", 1)
    for doc in originals["client_scripts"]:
        frappe.db.set_value("Client Script", doc["name"], "enabled", 0)
    for doc in originals["custom_fields"]:
        frappe.db.delete("Custom Field", {"name": doc["name"]})
    frappe.clear_cache()
