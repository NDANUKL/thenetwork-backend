"""Project-specific location mapping and verification for the native backend."""
import json
import frappe

LOCATION_FIELDS = ["site_label", "location_mode", "county", "area", "map_url", "latitude", "longitude", "pin_type", "contact_name", "contact_phone", "access_notes"]

def sync_locations(target, source, project):
    sites = source.get("customer_sites") or []
    if not sites:
        return
    for original in sites:
        raw_ids = original.get("project_ids")
        if raw_ids:
            try:
                member = project["id"] in json.loads(raw_ids)
            except (TypeError, ValueError):
                frappe.throw("Invalid site project IDs.")
        elif source.get("project_contract_version"):
            frappe.throw("A submitted location is missing its project IDs.")
        else:
            label = (original.site_label or "").split(":", 1)[0].replace("Projects ", "").replace("Project ", "").split("/", 1)[0]
            member = str(project["number"]) in [part.strip() for part in label.split("&")]
        if not member:
            continue
        values = {field: original.get(field) for field in LOCATION_FIELDS}
        snapshot = json.dumps(values, sort_keys=True)
        existing = next((row for row in target.get("project_locations") or [] if row.get("source_site_id") == original.name or (not row.get("source_site_id") and row.site_label == original.site_label)), None)
        if not existing:
            existing = target.append("project_locations", {**values, "original_location": original.get("original_location"), "confirmation_status": "Needs confirmation"})
        elif existing.get("source_location_snapshot"):
            previous = json.loads(existing.source_location_snapshot)
            if previous != values:
                existing.update(values)
                existing.confirmation_status = "Needs confirmation"
        existing.source_site_id = original.name
        existing.source_location_snapshot = snapshot

def validate_locations(doc):
    if not doc.diaspora_request:
        return
    if not doc.get("project_locations"):
        doc.dd_site_locations = "[]"
        return
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    destinations = []
    for site in doc.get("project_locations") or []:
        if site.get("location_verified") is not None:
            site.confirmation_status = "Confirmed for dispatch" if site.get("location_verified") else "Needs confirmation"
        prior = next((row for row in previous.get("project_locations") or [] if row.name == site.name), None) if previous else None
        if site.county not in [value.strip() for value in (doc.county or "").split(",")]:
            frappe.throw("County comes from the customer project and cannot be changed here.")
        changed = prior and any(site.get(key) != prior.get(key) for key in ["latitude", "longitude", "pin_type", "contact_name", "contact_phone", "access_notes"])
        if changed and prior.confirmation_status == "Confirmed for dispatch":
            site.confirmation_status = "Needs confirmation"
            site.location_verified = 0
        if bool(site.latitude) != bool(site.longitude):
            frappe.throw("Enter both latitude and longitude.")
        if site.latitude:
            try:
                latitude, longitude = float(site.latitude), float(site.longitude)
            except (TypeError, ValueError):
                frappe.throw("Invalid project coordinates.")
            if latitude != latitude or longitude != longitude or abs(latitude) > 90 or abs(longitude) > 180:
                frappe.throw("Invalid project coordinates.")
            site.map_url = f"https://www.google.com/maps/search/?api=1&query={site.latitude},{site.longitude}"
        if site.confirmation_status == "Confirmed for dispatch":
            if not site.latitude or not site.longitude or site.pin_type == "Approximate area":
                frappe.throw("Confirm a precise entrance or meeting point before dispatch.")
            if site.pin_type == "Meeting point" and not all([site.contact_name, site.contact_phone, site.access_notes]):
                frappe.throw("Confirm meeting contact and access instructions before dispatch.")
            site.confirmed_by = prior.confirmed_by if prior and prior.confirmation_status == "Confirmed for dispatch" and not changed else frappe.session.user
            site.confirmed_at = prior.confirmed_at if prior and prior.confirmation_status == "Confirmed for dispatch" and not changed else frappe.utils.now_datetime()
            destinations.append({key: site.get(key) for key in LOCATION_FIELDS})
        else:
            site.confirmed_by = site.confirmed_at = None
    doc.dd_site_locations = json.dumps(destinations)

def map_task_navigation(doc, request):
    sites = request.get("project_locations") or []
    if doc.is_new() and request.get("requires_verified_location") and (not sites or any(site.confirmation_status != "Confirmed for dispatch" for site in sites)):
        frappe.throw("Verify all project locations before assigning a scout.")
    doc.dd_site_locations = request.get("dd_site_locations")
    if not doc.location and len(sites) == 1 and sites[0].confirmation_status == "Confirmed for dispatch":
        site = sites[0]
        code = request.name + "-" + site.name
        location = frappe.db.get_value("FP Location", {"location_code": code}, "name")
        if not location:
            point = frappe.get_doc({"doctype": "FP Location", "location_code": code, "location_name": site.site_label, "latitude": float(site.latitude), "longitude": float(site.longitude), "address": site.area + ", " + site.county, "status": "Active", "geofence_radius_m": 50})
            point.insert(ignore_permissions=True)
            location = point.name
        doc.location = location
    if doc.is_new() and len(sites) > 1 and not doc.location:
        frappe.throw("Choose the verified visit location for this scout task.")

def sync_task_navigation(doc, method=None):
    if not doc.diaspora_request:
        return
    sites = doc.get("project_locations") or []
    verified = bool(sites) and all(site.confirmation_status == "Confirmed for dispatch" for site in sites)
    for task in frappe.get_all("Field Task", filters={"field_request": doc.name, "status": ["not in", ["Approved", "Cancelled"]]}, fields=["name", "location"]):
        values = {"due_at": str(doc.deadline)[:10] + " 23:59:59" if doc.deadline else None}
        if verified:
            values["dd_site_locations"] = doc.dd_site_locations
            if len(sites) == 1 and task.location and frappe.db.get_value("FP Location", task.location, "location_code") == doc.name + "-" + sites[0].name:
                site = sites[0]
                frappe.db.set_value("FP Location", task.location, {"latitude": float(site.latitude), "longitude": float(site.longitude), "address": site.area + ", " + site.county})
        frappe.db.set_value("Field Task", task.name, values)
