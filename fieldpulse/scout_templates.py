"""Versioned questionnaires transcribed from the owner's revised PDF."""
import hashlib
import json
import re
from pathlib import Path
import frappe
from fieldpulse.school_fees import apply_policy, LEGACY_TITLE, TITLE


def catalogue():
    return apply_policy(json.loads((Path(__file__).parent / "configuration/scout-questionnaires.json").read_text(encoding="utf-8")))


SHARED = [
    ("S1", "Are you at the assigned site, and does the location match the address, map pin and landmarks in the task?", ["Matches", "Location mismatch", "Unable to establish"], "Confirm the address or landmarks observed. Explain any mismatch. GPS is checked automatically before Start."),
    ("S2", "What access did you obtain, and which areas or items did you inspect?", ["Full access", "Partial access", "No access"], "Identify inspected areas or items and who granted access by role. Explain restrictions and affected checks."),
    ("S3", "Did anyone provide information you used in your answers?", ["Yes", "No - my answers are based on my observations only"], "If Yes, record each source's role, attributed statement and related question separately. Collect names only where necessary and permitted."),
    ("S4", "Were you able to complete all the assigned checks?", ["All assigned checks completed", "Some checks not completed", "No assigned checks completed"], "For each incomplete check identify what was unchecked, why, and the access or follow-up needed."),
]


def preserve_existing_published(name, preserve_published=False):
    """Migration may retain historical publications, never bless or rewrite drift."""
    if not preserve_published or frappe.db.get_value('FP Questionnaire', name, 'status') != 'Published':
        return False
    frappe.logger('fieldpulse').warning(
        'Preserved published questionnaire %s: source hash differs. '
        'No questions or hashes were changed; publish revised content as a new version.', name)
    return True


def install_templates(preserve_published=False):
    """Normal install/migration publishes the streamlined library by default."""
    from fieldpulse.scout_v2 import install_templates as install_v2
    install_v2(preserve_published=preserve_published)


def install_legacy_templates(preserve_published=False):
    """Explicit historical import only; not called by install or migration."""
    data = catalogue()
    for service in data["services"]:
        code = "DD-" + service["service_code"]
        version = service.get("questionnaire_version", data["version"])
        name = f"{code}-v{version}"
        digest = hashlib.sha256(json.dumps(service, sort_keys=True).encode()).hexdigest()
        existing = frappe.db.exists("FP Questionnaire", name) or frappe.db.get_value("FP Questionnaire", {"questionnaire_code": code, "version": version}, "name")
        if existing:
            if frappe.db.get_value("FP Questionnaire", existing, "schema_hash") != digest:
                if preserve_existing_published(existing, preserve_published):
                    continue
                frappe.throw("Questionnaire source changed: publish a new version instead of overwriting " + name)
            continue
        doc = frappe.get_doc(dict(doctype="FP Questionnaire", questionnaire_code=code,
            title=service["title"], service_code=service["service_code"], version=version,
            status="Draft", description=service["description"], schema_hash=digest, source_sha256=data["source_sha256"]))
        doc.insert(ignore_permissions=True, set_name=name)
        rows = [dict(code=key, label=label, detail=detail, group="shared", result_options=options) for key, label, options, detail in SHARED]
        rows += [dict(q, group="service") for q in service["questions"]]
        rows += [dict(code="S_EXTRA", label="Additional observations or answers", detail="Add anything not covered above. Explain unchecked items and follow-up needed.", group="final")]
        for sequence, row in enumerate(rows, 1):
            config = dict(group=row["group"], result_options=row.get("result_options", []),
                mandatory_evidence=row.get("mandatory_evidence", False), evidence_prompt=row.get("evidence_prompt", ""),
                source_question=row["code"], demonstration_required=bool(re.search(r"demonstrat", row["detail"], re.I)), protocol_version=1)
            frappe.get_doc(dict(doctype="FP Question", questionnaire=name, question_code=row["code"],
                label=row["label"], help_text=row["detail"], question_type="service_check", sequence=sequence,
                required=int(row["group"] != "final"), active=1, question_group={"shared":"Shared", "service":"Service", "final":"Final review"}[row["group"]], validation_json=json.dumps(config))).insert(ignore_permissions=True)
        doc.status = "Published"
        doc.published_at = frappe.utils.now_datetime()
        doc.save(ignore_permissions=True)


def infer_service(text, request_type=""):
    """Ambiguous services require coordinator selection; never silently call a building a plot."""
    text = (text or "").lower()
    groups = {
        "construction": r"construction|building progress|roofing|foundation|milestone",
        "land": r"\bland\b|\bplot\b|\bparcel\b",
        "property": r"\bhouse\b|\bhome\b|\bapartment\b|\bbuilding condition\b",
        "vehicle": r"\bvehicle\b|\bcar\b|\btruck\b|\bmotorbike\b",
        "equipment": r"\bequipment\b|\bmachine\b|\bfunded asset\b",
        "adult_enrolment": r"enrolment|enrollment",
        "university_fees": r"\bfees?\b|tuition",
        "adult_attendance": r"attendance",
        "adult_clinic": r"\bclinic\b|\bhospital visit\b",
        "document": r"\bdocument\b|\bcertificate\b",
        "receipt": r"\breceipt\b",
        "delivery": r"\bdelivery\b|\bdelivered\b|\bpurchase confirmation\b",
        "merchant_survey": r"\bsurvey\b|\binterviews?\b",
        "business": r"\bshop\b|\bbusiness\b|\bmerchant\b",
    }
    found = {key for key, pattern in groups.items() if re.search(pattern, text)}
    # These compound phrases define a more specific service.
    if "construction" in found and found <= {"construction", "land", "property"}:
        if request_type == "Construction Progress": return "construction"
        if "land" in found and request_type == "Property Verification": return "land"
        if found == {"construction"}: return "construction"
    if "merchant_survey" in found and found <= {"merchant_survey", "business"}: return "merchant_survey"
    if found.intersection({"adult_enrolment", "adult_attendance", "adult_clinic"}) and not re.search(r"\badult\b|\buniversity\b|\bcollege\b", text): return None
    if "university_fees" in found and found <= {"university_fees", "receipt"} and re.search(r"school|university|college|tuition", text): return "university_fees"
    if len(found) == 1: return next(iter(found))
    if not found and request_type == "Construction Progress": return "construction"
    if not found and request_type == "General Site Visit": return "general_visit"
    return None


def prepare_project(doc, method=None):
    if doc.get("scout_service") == LEGACY_TITLE:
        doc.scout_service = TITLE
    if not doc.get("scout_service"):
        doc.scout_service = infer_service(doc.get("project_title"), "") or infer_service((doc.get("project_title") or "") + " " + (doc.get("field_brief") or ""), doc.get("request_type"))
    if not doc.get("scout_service"): return
    services = catalogue()["services"]
    service = next((row for row in services if doc.scout_service in (row["service_code"], row["title"])), None)
    if not service: frappe.throw("Choose a service from the revised questionnaire library")
    code = service["service_code"]
    doc.scout_service = service["title"]
    filters = {"service_code": code, "status": "Published", "project": ["is", "not set"]}
    version = 3 if getattr(frappe, 'conf', {}).get('dd_scout_visit_workflow_enabled') else 2
    filters['version'] = version + 3 if code == 'university_fees' else version
    name = frappe.db.get_value("FP Questionnaire", filters, "name", order_by="version desc")
    previous_template = doc.get("scout_questionnaire")
    if previous_template and frappe.db.get_value("FP Questionnaire",previous_template,"project"):
        frappe.throw("Select a shared source template; project-specific versions are assigned automatically")
    # Do not switch an existing project's pinned version just because a newer one was published.
    if previous_template and frappe.db.get_value("FP Questionnaire", previous_template, "service_code") == code and frappe.db.get_value("FP Questionnaire", previous_template, "status") == "Published":
        name = previous_template
    if not name: frappe.throw("Publish the service questionnaire before dispatch")
    questions = frappe.get_all("FP Question", filters={"questionnaire": name, "active": 1}, fields=["name", "question_code", "label", "help_text", "validation_json"])
    service_rows = [q for q in questions if json.loads(q.validation_json or "{}").get("group") == "service"]
    if previous_template != name or not doc.get("scout_checks"):
        doc.scout_checks_confirmed = 0
        doc.set("scout_checks", [{"question": q.name} for q in service_rows if not json.loads(q.validation_json or '{}').get('assigned_only')])
    selected = [row.question for row in doc.get("scout_checks") or [] if row.get("question")]
    allowed = {q.name for q in service_rows}
    mandatory = {q.name for q in service_rows if json.loads(q.validation_json or "{}").get("mandatory_evidence") or json.loads(q.validation_json or '{}').get('mandatory_selection')}
    if len(selected) != len(set(selected)) or not set(selected) <= allowed or not mandatory <= set(selected):
        frappe.throw("Select unique questions from this service and retain its mandatory photo/video question")
    from fieldpulse.project_questionnaires import validate_draft, fingerprint, has_edits
    try: validate_draft(doc, questions)
    except (ValueError, TypeError) as error: frappe.throw(str(error))
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and previous.get("scout_checks_confirmed") and previous.get("scout_checks_confirmed") == doc.get("scout_checks_confirmed"):
        old = {row.question for row in previous.get("scout_checks") or []}
        if old != set(selected) or previous.get("scout_service") != doc.scout_service:
            doc.scout_checks_confirmed = 0
        configuration_fields = ('scout_authorisation', 'scout_reference_material', 'scout_contact_access', 'scout_restrictions')
        old_config = {row.question: row.get('configuration_json') for row in previous.get('scout_checks') or []}
        new_config = {row.question: row.get('configuration_json') for row in doc.get('scout_checks') or []}
        if old_config != new_config or any(previous.get(key) != doc.get(key) for key in configuration_fields): doc.scout_checks_confirmed = 0
    if previous and previous.get('scout_checks_confirmed') and fingerprint(previous) != fingerprint(doc):
        doc.scout_checks_confirmed = 0
    if doc.get('scout_checks_confirmed') and not has_edits(doc, questions) and any(json.loads(q.validation_json or '{}').get('protocol_version') == 2 for q in questions):
        from fieldpulse.scout_v2 import resolved_questions
        try: resolved_questions(doc, questions)
        except ValueError as error: frappe.throw(str(error))
    if doc.get("scout_checks_confirmed"):
        if not {'System Manager','Field Operations Coordinator'}.intersection(frappe.get_roles()):
            frappe.throw('Only coordinators may confirm a project questionnaire',frappe.PermissionError)
        if not previous or not previous.get('scout_checks_confirmed'):
            doc.scout_checks_reviewed_by = frappe.session.user
            doc.scout_checks_reviewed_at = frappe.utils.now_datetime()
        doc.alignment_review = int(not doc.get("county") or not doc.get("evidence_requirements"))
    doc.scout_questionnaire = name


def apply_to_task(doc, method=None):
    if not doc.is_new(): return
    if doc.get('replaces_task'):
        if frappe.flags.dd_replacement_source != doc.replaces_task:
            frappe.throw('Create replacement assignments through the coordinator rework action')
        source = frappe.get_doc('Field Task', doc.replaces_task)
        for key in ('field_request', 'location', 'questionnaire', 'questionnaire_scope', 'client_request_snapshot'):
            if doc.get(key) != source.get(key): frappe.throw('Keep the original assigned scope and site for the revisit')
        return
    if not doc.get("field_request"): return
    if frappe.db.exists('Field Task', {'field_request': doc.field_request, 'status': 'Awaiting authorization'}):
        frappe.throw('Resolve the pending revisit authorization before creating more assignments for this project')
    project = frappe.get_doc("Field Request", doc.field_request)
    if not project.get("diaspora_request") and not project.get("scout_service"): return
    prepare_project(project)
    if not project.get("scout_questionnaire"):
        frappe.throw("Choose the project's Scout service before assigning scouts; the service is ambiguous")
    if doc.get("questionnaire") and doc.questionnaire != project.scout_questionnaire:
        frappe.throw("Use the service questionnaire selected on the Field Request")
    if not project.get("scout_checks_confirmed"):
        frappe.throw("Review the selected service checks against the client request and confirm them on the Field Request before dispatch")
    doc.questionnaire = project.scout_questionnaire
    doc.questionnaire_version = frappe.db.get_value("FP Questionnaire", doc.questionnaire, "version")
    selected = {row.question for row in project.get("scout_checks") or [] if row.get("question")}
    questions = frappe.get_all("FP Question", filters={"questionnaire": doc.questionnaire, "active": 1}, fields=["name", "question_code", "label", "help_text", "validation_json"])
    from fieldpulse.project_questionnaires import apply_custom_task
    if apply_custom_task(doc, project, questions): return
    doc.questionnaire_scope = json.dumps([q.question_code for q in questions if q.name in selected or json.loads(q.validation_json or "{}").get("group") in {"shared", "final"}])
    snapshot = {"task_scope": project.field_brief, "service": project.scout_service, "site_or_item": project.get("project_title"), "evidence_tasks": project.get("evidence_requirements")}
    if any(json.loads(q.validation_json or '{}').get('protocol_version') == 2 for q in questions):
        from fieldpulse.scout_v2 import resolved_questions, snapshot_context, enabled
        if not enabled(): frappe.throw('Version 2 dispatch is disabled until compatible mobile rollout')
        try: resolved = resolved_questions(project, questions)
        except ValueError as error: frappe.throw(str(error))
        snapshot.update(snapshot_context(project), protocol_version=2, resolved_questions=resolved)
        if any(json.loads(q['validation_json']).get('visit_workflow_version') == 2 for q in resolved):
            from fieldpulse.scout_v2 import workflow_enabled
            if not workflow_enabled(): frappe.throw('New visit workflow dispatch is disabled until compatible mobile rollout')
            snapshot['visit_workflow_version'] = 2
        snapshot['service'] = frappe.db.get_value('FP Questionnaire', doc.questionnaire, 'title')
        if doc.get('location'):
            site = frappe.get_doc('FP Location', doc.location)
            snapshot['site_reference'] = {key:site.get(key) for key in ('location_name','address','latitude','longitude','geofence_radius_m')}
        if snapshot.get('visit_workflow_version') == 2 and not snapshot.get('site_reference'):
            frappe.throw('Assign a verified site before dispatching the visit workflow')
        doc.questionnaire_scope = json.dumps([q['question_code'] for q in resolved])
    if project.get("diaspora_request"):
        source = frappe.get_doc("Diaspora Request", project.diaspora_request)
        snapshot["client_request"] = source.original_brief
        rounds = frappe.get_all("DD Request Details", filters={"request": source.name, "status": ["in", ["Ready for review", "Closed"]]}, pluck="name", order_by="creation asc")
        snapshot["clarifications"] = [{"question": q.question, "answer": q.answer} for name in rounds for q in frappe.get_doc("DD Request Details", name).questions]
    from fieldpulse.project_questionnaires import review_snapshot
    snapshot['questionnaire_review'] = review_snapshot(project,api=frappe)
    doc.client_request_snapshot = json.dumps(snapshot)
