"""Native customer requests behavior, ported from the audited production definitions."""
import json
import frappe
from fieldpulse.beta_access import require_access
from fieldpulse.native_ownership import owned_event, owned_api

def customer_stage(source):
    """Describe coverage across all projects without changing operational statuses."""
    if source.status == "Rejected":
        return source.status
    from fieldpulse.project_alignment import project_plan
    plan = project_plan(source)
    structured = source.get("project_contract_version")
    key = "project_id" if structured else "project_number"
    expected = {project["id" if structured else "number"] for project in plan["projects"]}
    if not expected:
        return "New"
    projects = frappe.get_all("Field Request", filters={"diaspora_request": source.name,
        "status": ["!=", "Cancelled"]}, fields=[key, "status"])
    covered = {project.get(key) for project in projects
        if project.status in ("Assigned", "In Progress", "Completed")}
    if not expected.intersection(covered):
        return "New"
    if plan["issues"] or not expected.issubset(covered):
        return "Partially assigned"
    relevant = [project for project in projects if project.get(key) in expected]
    if all(project.status == "Completed" for project in relevant):
        return "Completed"
    if any(project.status in ("In Progress", "Completed") for project in relevant):
        return "In Progress"
    return "Fully assigned"


@frappe.whitelist()
@owned_api('DD Customer Request Records')
def requests(**kwargs):
    if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "parenttype": "User", "role": "System Manager"}):
        frappe.throw("Not permitted", frappe.PermissionError)
    email = (frappe.form_dict.get("email") or "").strip().lower()
    account_name = frappe.db.exists("DD Customer Account", {"user": email, "email_verified": 1})
    if not account_name or not frappe.db.get_value("User", email, "enabled") or frappe.db.get_value("User", email, "user_type") != "Website User":
        frappe.throw("Not permitted", frappe.PermissionError)
    roles = frappe.get_all("Has Role", filters={"parent": email, "parenttype": "User"}, pluck="role")
    if "DD Customer" not in roles or any(frappe.db.get_value("Role", role, "desk_access") for role in roles):
        frappe.throw("Not permitted", frappe.PermissionError)
    
    require_access(account_name)

    def row(item):
        stage = customer_stage(frappe.get_doc("Diaspora Request", item.name)) if item.status != "Rejected" else item.status
        actions = {"New": "Our team will review your request.", "Fully assigned": "Scouts have been assigned to all projects.", "Partially assigned": "Scouts have been assigned to some projects. Assignment is pending for the remaining projects.", "Awaiting assignment": "Scout assignment is pending.", "In Progress": "Fieldwork is in progress.", "Completed": "The request has been completed.", "Rejected": "Our team will explain the next steps."}
        return {"name": item.name, "title": item.summary or item.category_label or "Verification request",
            "status": "Details needed" if item.customer_action_required else stage, "modified": item.modified, "next_action": "Please complete the details needed form in your request." if item.customer_action_required else actions.get(stage, "Our team will update you here.")}
    
    action = frappe.form_dict.get("action")
    fields = ["name", "summary", "category_label", "status", "modified", "customer_action_required"]
    if action == "detail":
        reference = frappe.form_dict.get("reference") or ""
        name = frappe.db.exists("Diaspora Request", {"name": reference, "dd_customer_account": account_name})
        if not name:
            frappe.response["message"] = {"not_found": True}
        else:
            document = frappe.get_doc("Diaspora Request", name)
            result = row(document)
            result.update({"original_brief": document.original_brief, "location": document.get("county"),
                "stage": customer_stage(document)})
            location_keys = ["name", "site_label", "location_mode", "county", "area", "map_url", "latitude", "longitude", "pin_type", "contact_name", "contact_phone", "access_notes", "confirmation_status"]
            result["sites"] = []
            for site in document.get("customer_sites") or []:
                location = {}
                for key in location_keys:
                    location[key] = site.get(key)
                result["sites"].append(location)
            rounds = frappe.get_all("DD Request Details", filters={"request": name, "status": ["!=", "Draft"]}, fields=["name"], order_by="creation asc", limit_page_length=100)
            result["detail_rounds"] = []
            for item in rounds:
                detail = frappe.get_doc("DD Request Details", item.name)
                questions = []
                for q in detail.questions:
                    questions.append({"id": q.name, "question": q.question, "answer_type": q.answer_type, "site_name": q.site_name, "answer": q.answer, "location_answer": q.location_answer})
                result["detail_rounds"].append({"name": detail.name, "status": detail.status, "published_at": detail.published_at, "submitted_at": detail.submitted_at,
                    "questions": questions})
            frappe.response["message"] = {"request": result}
    elif action == "answer_details":
        reference = frappe.form_dict.get("reference") or ""
        name = frappe.db.exists("Diaspora Request", {"name": reference, "dd_customer_account": account_name})
        round_name = frappe.form_dict.get("round") or ""
        detail_name = frappe.db.exists("DD Request Details", {"name": round_name, "request": name}) if name else None
        if not detail_name:
            frappe.response["message"] = {"not_found": True}
        else:
            frappe.db.sql("SELECT name FROM `tabDD Request Details` WHERE name=%s FOR UPDATE", [detail_name])
            detail = frappe.get_doc("DD Request Details", detail_name)
            submission_id = frappe.form_dict.get("submission_id") or ""
            if not submission_id or len(submission_id) > 100:
                frappe.throw("Invalid response ID")
            if detail.status in ["Ready for review", "Closed"] and detail.submission_id == submission_id:
                frappe.response["message"] = {"success": True}
            elif detail.status != "Details needed":
                frappe.response["message"] = {"conflict": True}
            else:
                answers = frappe.form_dict.get("answers") or []
                if isinstance(answers, str):
                    answers = frappe.parse_json(answers)
                if not isinstance(answers, list) or len(answers) != len(detail.questions):
                    frappe.throw("Answer all questions")
                document = frappe.get_doc("Diaspora Request", name)
                for question in detail.questions:
                    matches = []
                    for response in answers:
                        if response.get("id") == question.name: matches.append(response)
                    if len(matches) != 1:
                        frappe.throw("Invalid answers")
                    answer = matches[0]
                    if question.answer_type == "Location":
                        location = answer.get("location")
                        if not isinstance(location, dict):
                            frappe.throw("Provide location details")
                        sites = []
                        for candidate in document.get("customer_sites") or []:
                            if candidate.name == question.site_name: sites.append(candidate)
                        if not sites:
                            frappe.throw("The site is no longer available")
                        site = sites[0]
                        for key in ["location_mode", "county", "area", "map_url", "latitude", "longitude", "pin_type", "contact_name", "contact_phone", "access_notes"]:
                            site.set(key, location.get(key) or "")
                        site.confirmation_status = "Needs confirmation"
                        site.location_verified = 0
                        question.location_answer = json.dumps(location)
                        question.answer = "Updated location details for " + site.site_label
                    else:
                        text = answer.get("answer") or ""
                        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                            frappe.throw("Provide an answer of up to 4000 characters")
                        question.answer = text.strip()
                document.save(ignore_permissions=True)
                detail.status = "Ready for review"
                detail.submission_id = submission_id
                detail.submitted_at = frappe.utils.now_datetime()
                detail.flags.dd_customer_response = True
                detail.save(ignore_permissions=True)
                frappe.response["message"] = {"success": True}
    elif action == "overview":
        recent = frappe.get_all("Diaspora Request", filters={"dd_customer_account": account_name}, fields=fields, order_by="modified desc, name desc", limit_page_length=5)
        counts = {"active_requests": frappe.db.count("Diaspora Request", {"dd_customer_account": account_name, "status": ["not in", ["Completed", "Rejected"]]}),
            "completed_requests": frappe.db.count("Diaspora Request", {"dd_customer_account": account_name, "status": "Completed"})}
        # Only coordinator-published next actions count as requiring customer response.
        counts["awaiting_response"] = frappe.db.count("Diaspora Request", {"dd_customer_account": account_name, "customer_action_required": 1})
        frappe.response["message"] = {"counts": counts, "requests": [row(item) for item in recent]}
    elif action == "requests":
        page = max(1, min(10000, frappe.utils.cint(frappe.form_dict.get("page") or 1)))
        filter_name = frappe.form_dict.get("filter") or "all"
        page_size = 20 if filter_name == "disputable" else 5
        filters = {"dd_customer_account": account_name}
        if filter_name == "completed":
            filters["status"] = "Completed"
        elif filter_name == "rejected":
            filters["status"] = "Rejected"
        elif filter_name == "active":
            filters["status"] = ["not in", ["Completed", "Rejected"]]
        elif filter_name == "action":
            filters["customer_action_required"] = 1
        elif filter_name == "draft":
            # The existing intake draft is local to the browser, not a submitted record.
            filters["name"] = ""
        search = (frappe.form_dict.get("search") or "")[:100]
        search_filters = [["name", "like", "%" + search + "%"], ["summary", "like", "%" + search + "%"]] if search else []
        items = frappe.get_all("Diaspora Request", filters=filters, or_filters=search_filters, fields=fields, order_by="modified desc, name desc", limit_start=(page - 1) * page_size, limit_page_length=page_size + 1)
        frappe.response["message"] = {"requests": [row(item) for item in items[:page_size]], "has_more": len(items) > page_size}
    else:
        frappe.throw("Invalid action")
    return frappe.response.pop("message", None)

@owned_event('DD Request Customer Ownership')
def validate_ownership(doc, method=None):
    # The customer link is immutable once set, including during staff edits.
    previous = frappe.db.get_value("Diaspora Request", doc.name, "dd_customer_account") if not doc.is_new() else None
    if doc.dd_customer_account and not previous:
        account = frappe.get_doc("DD Customer Account", doc.dd_customer_account)
        if not account.email_verified or not frappe.db.get_value("User", account.user, "enabled"):
            frappe.throw("A verified customer account is required")
    if previous and previous != doc.dd_customer_account:
        frappe.throw("Customer ownership cannot be changed")

@owned_event('DD Field Customer Ownership')
def copy_ownership(doc, method=None):
    # Operations requests inherit ownership from their source, never from an email.
    doc.dd_customer_account = frappe.db.get_value("Diaspora Request", doc.diaspora_request, "dd_customer_account") if doc.diaspora_request else None

@owned_event('DD Request Locations')
def validate_locations(doc, method=None):
    previous = frappe.get_doc("Diaspora Request", doc.name) if not doc.is_new() else None
    for site in doc.get("customer_sites") or []:
        prior = None
        if previous:
            for old_site in previous.get("customer_sites") or []:
                if old_site.name == site.name:
                    prior = old_site
        if not prior:
            if site.location_mode == "approximate":
                frappe.throw("Choose a map pin or a local contact for this site.")
            if site.location_mode == "known" and (not site.latitude or not site.longitude or site.pin_type == "Approximate area"):
                frappe.throw("Select the site entrance or meeting point and provide its coordinates.")
            if site.location_mode == "contact" and (not site.contact_name or not site.contact_phone):
                frappe.throw("Provide the local contact name and phone number.")
        check_contact = not prior
        if prior and (site.contact_phone != prior.contact_phone or site.access_notes != prior.access_notes or site.location_mode != prior.location_mode):
            check_contact = True
        if check_contact:
            phone = site.contact_phone or ""
            if phone and (len(phone) != 10 or phone[:2] not in ["07", "01", "02"] or not phone.isdigit()):
                frappe.throw("Enter a Kenyan contact number with 10 digits starting with 07, 01 or 02.")
            if site.location_mode == "contact" and not (site.access_notes or "").strip():
                frappe.throw("Provide landmarks, access instructions and who can meet the scout.")
        if not site.original_location:
            site.original_location = json.dumps({"site_label": site.site_label, "county": site.county, "area": site.area, "map_url": site.map_url, "latitude": site.latitude, "longitude": site.longitude, "pin_type": site.pin_type, "contact_name": site.contact_name, "contact_phone": site.contact_phone, "access_notes": site.access_notes})
        if prior:
            site.original_location = prior.original_location
        if bool(site.latitude) != bool(site.longitude):
            frappe.throw("Provide both latitude and longitude")
        if site.latitude:
            try:
                latitude = float(site.latitude)
                longitude = float(site.longitude)
            except (ValueError, TypeError):
                frappe.throw("Invalid coordinates")
            if latitude != latitude or longitude != longitude or abs(latitude) > 90 or abs(longitude) > 180:
                frappe.throw("Invalid coordinates")
        changed = not prior
        if prior:
            for key in ["latitude", "longitude", "map_url", "pin_type", "contact_name", "contact_phone", "access_notes"]:
                if site.get(key) != prior.get(key): changed = True
        if site.get("location_verified") is not None:
            site.confirmation_status = "Confirmed for dispatch" if site.get("location_verified") else "Needs confirmation"
        if prior and prior.confirmation_status == "Confirmed for dispatch" and changed:
            site.confirmation_status = "Needs confirmation"
            site.location_verified = 0
        if site.confirmation_status == "Confirmed for dispatch":
            if not site.latitude or not site.longitude or site.pin_type == "Approximate area":
                frappe.throw("Confirm an entrance or meeting point with coordinates before dispatch")
            if site.pin_type == "Meeting point" and (not site.contact_name or not site.contact_phone or not site.access_notes):
                frappe.throw("A meeting point needs a local contact and meeting arrangements")
            if not prior or prior.confirmation_status != "Confirmed for dispatch":
                site.confirmed_by = frappe.session.user
                site.confirmed_at = frappe.utils.now_datetime()
            else:
                site.confirmed_by = prior.confirmed_by
                site.confirmed_at = prior.confirmed_at
        else:
            site.confirmed_by = None
            site.confirmed_at = None
