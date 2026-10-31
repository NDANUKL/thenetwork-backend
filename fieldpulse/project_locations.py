"""Project-specific location mapping and verification for the native backend."""
import json
import frappe

LOCATION_FIELDS = ["site_label", "location_mode", "county", "area", "map_url", "latitude", "longitude", "pin_type", "contact_name", "contact_phone", "access_notes"]
LOCATION_LOCKED_TASK_STATUSES = ("Accepted", "In Progress", "Submitted", "Approved", "Cancelled")


def contact_access_summary(sites):
    """Keep each destination's arrangements together; never mix project contacts."""
    blocks = []
    for index, site in enumerate(sites or [], 1):
        name = str(site.get("contact_name") or "").strip()
        phone = str(site.get("contact_phone") or "").strip()
        notes = str(site.get("access_notes") or "").strip()
        if not any((name, phone, notes)):
            continue
        lines = [str(site.get("site_label") or f"Location {index}").strip()]
        if name or phone:
            lines.append("Contact: " + " - ".join(value for value in (name, phone) if value))
        if notes:
            lines.append("Access: " + notes)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def sync_contact_access(doc):
    if doc.get("diaspora_request"):
        doc.scout_contact_access = contact_access_summary(doc.get("project_locations"))


def can_correct_project_location(doc):
    """An Assigned task has not started; accepted or progressed work locks its pin."""
    return not frappe.db.exists("Field Task", {
        "field_request": doc.name,
        "status": ["in", list(LOCATION_LOCKED_TASK_STATUSES)],
    })


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
        source_verified = bool(original.get("location_verified"))
        snapshot = json.dumps({**values, "_source_verified": source_verified}, sort_keys=True)
        existing = next((row for row in target.get("project_locations") or [] if row.get("source_site_id") == original.name or (not row.get("source_site_id") and row.site_label == original.site_label)), None)
        previous_verified = None
        new_row = not existing
        if new_row:
            existing = target.append("project_locations", {**values, "original_location": original.get("original_location"), "confirmation_status": "Needs confirmation", "location_verified": 0})
        elif existing.get("source_location_snapshot"):
            previous = json.loads(existing.source_location_snapshot)
            previous_verified = previous.pop("_source_verified", None)
            if previous != values:
                existing.update(values)
                existing.confirmation_status = "Needs confirmation"
                existing.location_verified = 0
        # Only a source confirmation change should override a project's own review.
        # Never apply confirmation to a different destination corrected on that project.
        verification_changed = (previous_verified is not None and previous_verified != source_verified) or (previous_verified is None and source_verified) or new_row
        if verification_changed and all(existing.get(key) == value for key, value in values.items()):
            existing.location_verified = int(source_verified)
            existing.confirmation_status = "Confirmed for dispatch" if source_verified else "Needs confirmation"
        existing.source_site_id = original.name
        existing.source_location_snapshot = snapshot

def validate_locations(doc):
    if not doc.diaspora_request:
        return
    sync_contact_access(doc)
    if not doc.get("project_locations"):
        doc.dd_site_locations = "[]"
        return
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and not can_correct_project_location(doc):
        for site in doc.get("project_locations") or []:
            prior = next((row for row in previous.get("project_locations") or [] if row.name == site.name), None)
            if prior and any(site.get(key) != prior.get(key) for key in ["latitude", "longitude", "pin_type", "contact_name", "contact_phone", "access_notes"]):
                frappe.throw("Location corrections are available only before a scout accepts or starts the task.")
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
        frappe.throw("Tick Location verified for each site on the customer request and save before assigning a scout.")
    doc.dd_site_locations = request.get("dd_site_locations")
    if not doc.location and len(sites) == 1 and sites[0].confirmation_status == "Confirmed for dispatch":
        site = sites[0]
        code = request.name + "-" + site.name
        location = frappe.db.get_value("FP Location", {"location_code": code}, "name")
        if not location:
            point = frappe.get_doc({"doctype": "FP Location", "location_code": code, "location_name": site.site_label, "latitude": str(site.latitude), "longitude": str(site.longitude), "address": site.area + ", " + site.county, "status": "Active", "geofence_radius_m": 50})
            point.insert(ignore_permissions=True)
            location = point.name
        doc.location = location
    if doc.is_new() and len(sites) > 1 and not doc.location:
        frappe.throw("Choose the verified visit location for this scout task.")


def refresh_assigned_task_pins(location):
    """Refresh only Task Brief pins whose scout work has not started."""
    tasks = frappe.get_all("Field Task", filters={
        "location": location.name,
        "status": "Assigned",
        "task_brief_version": ["is", "set"],
    }, fields=["name", "task_brief_snapshot"])
    try:
        latitude, longitude = float(location.latitude), float(location.longitude)
    except (TypeError, ValueError):
        frappe.throw("Correct the location coordinates before syncing assigned tasks.")

    for task in tasks:
        try:
            pinned = json.loads(task.task_brief_snapshot or "{}")
        except (TypeError, ValueError):
            continue
        site = pinned.get("site")
        if pinned.get("contract_version") != 1 or not isinstance(site, dict):
            continue
        site.update(
            latitude=latitude,
            longitude=longitude,
            radius_m=float(location.geofence_radius_m or 50),
            label=location.get("location_name"),
            address=location.get("address"),
        )
        frappe.db.set_value(
            "Field Task", task.name,
            "task_brief_snapshot", json.dumps(pinned, ensure_ascii=False),
        )

def sync_task_navigation(doc, method=None):
    if not doc.diaspora_request:
        return
    sites = doc.get("project_locations") or []
    verified = bool(sites) and all(site.confirmation_status == "Confirmed for dispatch" for site in sites)
    for task in frappe.get_all("Field Task", filters={"field_request": doc.name, "status": ["not in", ["Approved", "Cancelled", "Rejected"]]}, fields=["name", "location", "status", "task_brief_snapshot"]):
        values = {"due_at": str(doc.deadline)[:10] + " 23:59:59" if doc.deadline else None}
        if verified and task.status == "Assigned":
            values["dd_site_locations"] = doc.dd_site_locations
            code = frappe.db.get_value("FP Location", task.location, "location_code") if task.location else None
            site = next((item for item in sites if code == doc.name + "-" + item.name), None)
            if site and task.location:
                address = ", ".join(value for value in (site.area, site.county) if value)
                location_values = {"latitude": str(site.latitude), "longitude": str(site.longitude), "address": address}
                frappe.db.set_value("FP Location", task.location, location_values)
                # A not-yet-started assignment may receive its corrected pin.
                # Once accepted or started, its Task Brief snapshot stays immutable.
                if task.status == "Assigned" and task.task_brief_snapshot:
                    pinned = json.loads(task.task_brief_snapshot)
                    if pinned.get("contract_version") == 1 and isinstance(pinned.get("site"), dict):
                        pinned["site"].update(latitude=location_values["latitude"], longitude=location_values["longitude"],
                            radius_m=frappe.db.get_value("FP Location", task.location, "geofence_radius_m") or 50,
                            accuracy_threshold_m=doc.get("gps_accuracy_threshold_m") or 20,
                            label=site.site_label, address=address)
                        frappe.db.set_value("Field Task", task.name, "task_brief_snapshot", json.dumps(pinned, ensure_ascii=False))
        frappe.db.set_value("Field Task", task.name, values)
