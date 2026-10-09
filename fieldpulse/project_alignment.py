"""Native versions of the Diaspora Desk project alignment scripts."""
import json
import frappe

# Ported from frappe/alignment/common.py; assignment remains permission checked.
def check_project_access(source):
    # No customer-record role permissions are added. Automation can use an
    # existing operational request only when the caller can write that request.
    allowed = source.has_permission("read")
    if not allowed:
        linked = frappe.get_all("Field Request", filters={"diaspora_request": source.name}, fields=["name"])
        for row in linked:
            request = frappe.get_doc("Field Request", row.name)
            if request.has_permission("write"):
                allowed = True
    if not allowed:
        frappe.throw("You cannot map projects from this customer request.", frappe.PermissionError)


def project_plan(source):
    counties = "Mombasa|Kwale|Kilifi|Tana River|Lamu|Taita Taveta|Garissa|Wajir|Mandera|Marsabit|Isiolo|Meru|Tharaka Nithi|Embu|Kitui|Machakos|Makueni|Nyandarua|Nyeri|Kirinyaga|Murang'a|Kiambu|Turkana|West Pokot|Samburu|Trans Nzoia|Uasin Gishu|Elgeyo Marakwet|Nandi|Baringo|Laikipia|Nakuru|Narok|Kajiado|Kericho|Bomet|Kakamega|Vihiga|Bungoma|Busia|Siaya|Kisumu|Homa Bay|Migori|Kisii|Nyamira|Nairobi".split("|")
    county_keys = {}
    for county in counties:
        county_keys["".join(c for c in county.lower() if c.isalpha())] = county
    projects = {}
    issues = []
    try:
        details = json.loads(source.get("project_details") or "[]")
    except (TypeError, ValueError):
        frappe.throw("Project details must be a JSON array.")
    if not isinstance(details, list):
        frappe.throw("Project details must be a JSON array.")
    for detail in details:
        if not isinstance(detail, dict):
            frappe.throw("Each project detail must be an object.")
        number = detail.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            issues.append("A project detail needs a positive integer project number.")
            continue
        if number in projects:
            issues.append("Duplicate project number " + str(number))
            continue
        description = detail.get("description") or ""
        raw_county = detail.get("county") or ""
        county = county_keys.get("".join(c for c in raw_county.lower().replace("county", "") if c.isalpha()), "")
        if not county:
            for candidate in counties:
                if candidate.lower() + " county" in description.lower():
                    county = candidate
        if number and description:
            projects[number] = {"number": number, "title": description, "county": county, "request_type": "General Site Visit", "evidence": [], "description": description, "scope_status": detail.get("location_question_status")}
    for row in source.get("evidence_checklist") or []:
        text = (row.get("evidence_item") or "").strip()
        number = 0
        title = ""
        county = ""
        if text.lower().startswith("project ") and "[" in text and "]" in text:
            prefix = text.split("[", 1)[0].strip().split()
            if len(prefix) == 2 and prefix[1].isdigit():
                number = int(prefix[1])
            label = text.split("[", 1)[1].split("]", 1)[0]
            # Intake labels may use a middle dot or a spaced dash.
            label = label.replace(" – ", "·").replace(" — ", "·").replace(" - ", "·")
            parts = label.split("·")
            if len(parts) == 2:
                title = parts[0].strip()
                raw_county = parts[1].lower().replace("county", "")
                county = county_keys.get("".join(c for c in raw_county if c.isalpha()), "")
        if not number or not title or not county:
            issues.append("An evidence item needs a confirmed project number, title and county.")
        else:
            project = projects.get(number)
            if project and (project["county"] and project["county"] != county or not project.get("description") and project["title"] != title):
                issues.append("Conflicting county or title for project " + str(number))
            if not project:
                request_type = {"land_property_check": "Property Verification", "construction_progress": "Construction Progress", "business_asset_check": "Business / Merchant Verification"}.get(source.get("category"), "General Site Visit")
                if title.upper() in ["SHOP", "SALON", "BUSINESS", "MERCHANT"]:
                    request_type = "Business / Merchant Verification"
                elif title.upper() == "LAND":
                    request_type = "Property Verification"
                elif title.upper() in ["HOUSE", "HOME", "PLOT", "PROPERTY"] and source.get("category") != "construction_progress":
                    request_type = "Property Verification"
                project = {"number": number, "title": title, "county": county, "request_type": request_type, "evidence": []}
                projects[number] = project
            project["county"] = county
            project["title"] = title
            project["evidence"].append(text)
    for project in projects.values():
        text = (project.get("description") or project["title"]).lower()
        if "construction" in text:
            project["request_type"] = "Construction Progress"
        elif any(word in text for word in ["salon", "shop", "business", "merchant"]):
            project["request_type"] = "Business / Merchant Verification"
        elif any(word in text for word in ["land", "house", "home", "plot", "property", "apartment"]):
            project["request_type"] = "Construction Progress" if source.get("category") == "construction_progress" else "Property Verification"
        project["review"] = 1 if not project["county"] or not project["evidence"] or project.get("scope_status") in ["needed", "scope_confirmation", "unsupported"] else 0
    deadline = None
    preference = source.get("deadline_preference")
    if preference == "specific":
        deadline = source.get("deadline_date")
    elif preference in ["oneWeek", "twoWeeks"]:
        deadline = frappe.utils.add_days(str(source.get("creation") or frappe.utils.now())[:10], 7 if preference == "oneWeek" else 14)
    return {"projects": [projects[number] for number in sorted(projects)], "issues": issues, "deadline": str(deadline)[:10] if deadline else None}


def fill_field_request(target, source, plan):
    if plan["issues"] or not plan["projects"]:
        target.alignment_review = 1
        return
    number = target.get("project_number") or plan["projects"][0]["number"]
    selected = None
    for project in plan["projects"]:
        if project["number"] == number:
            selected = project
    if not selected:
        frappe.throw("This project is no longer in the customer request. Coordinator review is required.")
    initial = not target.get("project_number")
    if initial and not target.is_new() and (target.status != "Awaiting Assignment" or frappe.db.exists("Field Task", {"field_request": target.name})):
        frappe.throw("An existing assignment cannot be split automatically. Review its project scope first.")
    target.project_number = selected["number"]
    target.project_title = selected["title"]
    target.project_key = source.name + ":" + str(number)
    target.county = selected["county"]
    target.deadline_preference = source.deadline_preference
    target.customer_target_date = plan["deadline"]
    target.alignment_review = selected["review"]
    if not target.deadline:
        target.deadline = plan["deadline"]
    if initial or target.status == "Awaiting Assignment" and not frappe.db.exists("Field Task", {"field_request": target.name}):
        target.request_type = selected["request_type"]
    target.evidence_requirements = "\n".join(selected["evidence"])
    if initial or target.status == "Awaiting Assignment" and not frappe.db.exists("Field Task", {"field_request": target.name}):
        timing = {"flexible": "No fixed customer deadline", "oneWeek": "Within one week of submission", "twoWeeks": "Within two weeks of submission", "specific": "By the customer's selected date"}.get(source.deadline_preference, "")
        brief = selected.get("description") or ""
        for paragraph in (source.summary or "").split("\n\n"):
            if paragraph.strip().lower().startswith("project " + str(number) + ":"):
                brief = paragraph.strip()
        if len(plan["projects"]) == 1 and not brief:
            brief = source.summary or ""
        target.field_brief = "Project " + str(number) + ": " + selected["title"] + " — " + selected["county"] + "\n\n" + brief + "\n\nEvidence required:\n" + target.evidence_requirements + "\n\nCustomer timing: " + timing + (" (" + plan["deadline"] + ")" if plan["deadline"] else "")

def map_diaspora(doc, method=None):
    plan = project_plan(doc)
    doc.customer_target_date = plan["deadline"]
    doc.alignment_review = 1 if plan["issues"] or not plan["projects"] or any(project["review"] for project in plan["projects"]) else 0
    if not plan["issues"] and plan["projects"]:
        counties = []
        for project in plan["projects"]:
            if project["county"] not in counties:
                counties.append(project["county"])
            for row in doc.evidence_checklist:
                if row.evidence_item.strip() in project["evidence"]:
                    row.project_number = project["number"]
                    row.county = project["county"]
        doc.county = ", ".join(counties)

def map_field_request(doc, method=None):
    if doc.diaspora_request:
        source = frappe.get_doc("Diaspora Request", doc.diaspora_request)
        if not doc.is_new() and frappe.db.get_value("Field Request", doc.name, "diaspora_request") != doc.diaspora_request:
            frappe.throw("The customer request link cannot be changed on an existing project.")
        check_project_access(source)
        plan = project_plan(source)
        fill_field_request(doc, source, plan)

def expand_projects(doc, method=None):
    if doc.diaspora_request and doc.project_number:
        source = frappe.get_doc("Diaspora Request", doc.diaspora_request)
        check_project_access(source)
        plan = project_plan(source)
        if not plan["issues"]:
            for project in plan["projects"]:
                key = source.name + ":" + str(project["number"])
                if not frappe.db.exists("Field Request", {"project_key": key}):
                    target = frappe.get_doc({"doctype": "Field Request", "source": "Diaspora Desk", "source_reference": source.name, "diaspora_request": source.name, "project_number": project["number"], "project_title": project["title"], "project_key": key, "request_type": project["request_type"], "county": project["county"], "field_brief": "Project " + str(project["number"]) + ": " + project["title"] + " — " + project["county"] + "\n\n" + (source.summary or "") + "\n\nThis assignment covers only this project.\n\nEvidence required:\n" + "\n".join(project["evidence"]), "deadline": plan["deadline"], "priority": "Normal", "status": "Awaiting Assignment"})
                    # Trusted conversion hook; website integration has no general
                    # Field Request creation rights. Only source-derived projects are created.
                    target.insert(ignore_permissions=True)

def map_task(doc, method=None):
    if doc.field_request:
        request = frappe.get_doc("Field Request", doc.field_request)
        old_reference = frappe.db.get_value("Field Task", doc.name, "field_request") if not doc.is_new() else None
        if doc.is_new() or not old_reference:
            request.check_permission("write")
        elif old_reference != doc.field_request:
            frappe.throw("The project link cannot be changed on an existing scout task.")
        if request.alignment_review:
            frappe.throw("Confirm project scope and county on the Field Request before assigning scouts.")
        doc.project_number = request.project_number
        doc.project_title = request.project_title
        doc.county = request.county
        doc.request_type = request.request_type
        doc.evidence_requirements = request.evidence_requirements
        doc.priority = request.priority
        doc.task_brief = request.field_brief
        if not doc.due_at and request.deadline:
            doc.due_at = str(request.deadline)[:10] + " 23:59:59"
    elif doc.is_new() and not doc.legacy_fp_task:
        frappe.throw("New Field Tasks must link to a Field Request.")
    elif not doc.is_new() and frappe.db.get_value("Field Task", doc.name, "field_request"):
        frappe.throw("An existing scout task cannot be detached from its project.")

def rollup_tasks(doc, method=None):
    if doc.field_request:
        request = frappe.get_doc("Field Request", doc.field_request)
        tasks = frappe.get_all("Field Task", filters={"field_request": request.name, "status": ["!=", "Cancelled"]}, fields=["status"])
        if tasks and request.status != "Cancelled":
            status = "Assigned"
            if all(task.status == "Approved" for task in tasks):
                status = "Completed"
            elif any(task.status in ["Accepted", "In Progress", "Submitted", "Rejected", "Approved"] for task in tasks):
                status = "In Progress"
            if request.status != status:
                # Derived status only: a scout task update must not require
                # coordinator permissions or rewrite the parent project's scope.
                frappe.db.set_value("Field Request", request.name, "status", status)
            if request.diaspora_request:
                source = frappe.get_doc("Diaspora Request", request.diaspora_request)
                plan = project_plan(source)
                requests = frappe.get_all("Field Request", filters={"diaspora_request": source.name, "status": ["!=", "Cancelled"]}, fields=["project_number", "status"])
                expected = [project["number"] for project in plan["projects"]]
                covered = [row.project_number for row in requests]
                status = "Assigned"
                all_projects_present = True
                for number in expected:
                    if number not in covered:
                        all_projects_present = False
                if expected and not plan["issues"] and all_projects_present and requests and all(row.status == "Completed" for row in requests):
                    status = "Completed"
                elif any(row.status in ["In Progress", "Completed"] for row in requests):
                    status = "In Progress"
                if source.status != "Rejected" and source.status != status:
                    # Derived aggregate status only, not a general customer-record edit.
                    frappe.db.set_value("Diaspora Request", source.name, "status", status)

@frappe.whitelist(methods=["POST"])
def assign_project_scouts(field_request, assignments):
    name = field_request
    request = frappe.get_doc("Field Request", name)
    request.check_permission("write")
    if not frappe.has_permission("Field Task", "create"):
        frappe.throw("Not permitted to create Field Tasks", frappe.PermissionError)
    if request.alignment_review or (request.diaspora_request and not request.project_number) or not request.county:
        frappe.throw("Confirm the project's scope and county before assigning scouts.")
    if request.status in ["Completed", "Cancelled"]:
        frappe.throw("Cannot assign a completed or cancelled project.")
    try:
        assignments = json.loads(assignments) if isinstance(assignments, str) else assignments
    except (TypeError, ValueError):
        frappe.throw("Scout assignments must be a JSON array.")
    if not isinstance(assignments, list) or not all(isinstance(row, dict) for row in assignments):
        frappe.throw("Scout assignments must be a JSON array of objects.")
    if not assignments or len(assignments) > 20:
        frappe.throw("Choose between one and twenty scout assignments.")
    responsibilities = [(row.get("responsibility") or "").strip().casefold() for row in assignments]
    if len(assignments) > 1 and (not all(responsibilities) or len(set(responsibilities)) != len(responsibilities)):
        frappe.throw("Give each scout a distinct responsibility.")
    seen = []
    created = []
    for assignment in assignments:
        scout = assignment.get("scout")
        if not scout or scout in seen:
            frappe.throw("Choose each scout once.")
        seen.append(scout)
        profile = frappe.get_doc("Scout Profile", scout)
        profile.check_permission("read")
        responsibility = (assignment.get("responsibility") or "").strip()
        if len(assignments) > 1 and not responsibility:
            frappe.throw("Give each scout a responsibility when assigning multiple scouts.")
        existing = frappe.db.get_value("Field Task", {"field_request": name, "scout_profile": scout, "status": ["not in", ["Cancelled", "Approved"]]}, "name")
        if existing:
            created.append(existing)
        else:
            task = frappe.get_doc({"doctype": "Field Task", "field_request": name, "scout_profile": scout, "status": "Assigned", "assigned_at": frappe.utils.now(), "responsibility": responsibility, "location": assignment.get("location"), "questionnaire": assignment.get("questionnaire")})
            if task.questionnaire:
                task.questionnaire_version = frappe.db.get_value("FP Questionnaire", task.questionnaire, "version")
            task.insert()
            created.append(task.name)
    request = frappe.get_doc("Field Request", name)
    if request.status == "Awaiting Assignment":
        request.status = "Assigned"
        request.save()
    if request.diaspora_request:
        # Derived workflow status only; no direct customer-record edit permission.
        status = frappe.db.get_value("Diaspora Request", request.diaspora_request, "status")
        if status in ["New", "In Review"]:
            frappe.db.set_value("Diaspora Request", request.diaspora_request, "status", "Assigned")
    return {"tasks": created}



def repair_metadata():
    """Explicit bench repair; preserve projects that already have scout work."""
    user = frappe.get_doc("User", frappe.session.user)
    if not any(role.role == "System Manager" for role in user.roles):
        frappe.throw("Only a System Manager can run this metadata repair.", frappe.PermissionError)
    results = []
    sources = frappe.get_all("Diaspora Request", fields=["name"], limit_page_length=100000)
    for row in sources:
        source = frappe.get_doc("Diaspora Request", row.name)
        plan = project_plan(source)
        review = 1 if plan["issues"] or not plan["projects"] or any(p["review"] for p in plan["projects"]) else 0
        values = {"customer_target_date": plan["deadline"], "alignment_review": review}
        if not plan["issues"] and plan["projects"]:
            counties = []
            for project in plan["projects"]:
                if project["county"] not in counties:
                    counties.append(project["county"])
                for evidence in source.evidence_checklist:
                    if evidence.evidence_item.strip() in project["evidence"]:
                        frappe.db.set_value("Diaspora Request Evidence", evidence.name, {"project_number": project["number"], "county": project["county"]})
            values["county"] = ", ".join(counties)
        frappe.db.set_value("Diaspora Request", source.name, values)
        fields = frappe.get_all("Field Request", filters={"diaspora_request": source.name}, fields=["name", "status", "project_number"])
        repaired = []
        skipped = []
        for field in fields:
            if field.status != "Awaiting Assignment" or frappe.db.exists("Field Task", {"field_request": field.name}):
                skipped.append(field.name)
            else:
                target = frappe.get_doc("Field Request", field.name)
                target.check_permission("write")
                target.save()
                repaired.append(field.name)
        results.append({"request": source.name, "review": review, "repaired": repaired, "existing_assignments_preserved": skipped})
    return results
