"""Retire temporary conversion scripts only after native code is installed."""
import frappe

RETIRED = {
    "DD Submitted Project Contract": ("Diaspora Request", "Before Save"),
    "DD Field Project Mapping": ("Field Request", "Before Save"),
    "DD Field Project Expansion": ("Field Request", "After Save"),
    "DD Task Project Mapping": ("Field Task", "Before Save"),
    "DD Task Completion Rollup": ("Field Task", "After Save"),
    "DD Field Location Gate": ("Field Request", "Before Save"),
    "DD Location Navigation Sync": ("Diaspora Request", "After Save"),
}

def execute():
    if not frappe.conf.get("dd_native_handover_approved"):
        frappe.throw("Production scripts are retained until the owner explicitly approves native handover. Do not run retirement migrations yet.")
    # Import/contract checks must succeed before retiring the working live scripts.
    from fieldpulse.project_alignment import ensure_field_requests
    from fieldpulse.project_locations import sync_locations, validate_locations, sync_task_navigation
    from fieldpulse.project_contract import assert_project_coverage
    assert all(callable(fn) for fn in [ensure_field_requests, sync_locations, validate_locations, sync_task_navigation, assert_project_coverage])
    # These fields are now standard app schema. Never recreate duplicate Custom Fields.
    required = {
        "DD Request Site": {"project_ids", "source_site_id", "source_location_snapshot"},
        "Field Request": {"project_locations", "dd_site_locations", "requires_verified_location", "scope_confirmed", "scope_review_note"},
        "Field Task": {"dd_site_locations"},
    }
    for doctype, names in required.items():
        standard = frappe.get_doc("DocType", doctype)
        if not names.issubset({field.fieldname for field in standard.fields}):
            frappe.throw("Native project schema is incomplete: " + doctype)
    originals = []
    for name, (doctype, event) in RETIRED.items():
        if not frappe.db.exists("Server Script", name):
            continue
        script = frappe.get_doc("Server Script", name)
        if script.script_type != "DocType Event" or script.reference_doctype != doctype or script.doctype_event != event:
            frappe.throw("Unexpected script definition: " + name + "; review before retirement.")
        originals.append(script.as_dict())
    if originals:
        frappe.get_doc({"doctype": "File", "file_name": "before-permanent-project-contract.json", "is_private": 1, "content": frappe.as_json(originals)}).insert(ignore_permissions=True)
    for original in originals:
        frappe.db.set_value("Server Script", original["name"], "disabled", 1)
    frappe.clear_cache()
