"""Versioned questionnaires transcribed from the owner's revised PDF."""
import hashlib
import json
import re
from pathlib import Path
import frappe


def catalogue():
    return json.loads((Path(__file__).parent / "configuration/scout-questionnaires.json").read_text(encoding="utf-8"))


SHARED = [
    ("S1", "Are you at the assigned site, and does the location match the address, map pin and landmarks in the task?", ["Matches", "Location mismatch", "Unable to establish"], "Confirm the address or landmarks observed. Explain any mismatch. GPS is checked automatically before Start."),
    ("S2", "What access did you obtain, and which areas or items did you inspect?", ["Full access", "Partial access", "No access"], "Identify inspected areas or items and who granted access by role. Explain restrictions and affected checks."),
    ("S3", "Did anyone provide information you used in your answers?", ["Yes", "No - my answers are based on my observations only"], "If Yes, record each source's role, attributed statement and related question separately. Collect names only where necessary and permitted."),
    ("S4", "Were you able to complete all the assigned checks?", ["All assigned checks completed", "Some checks not completed", "No assigned checks completed"], "For each incomplete check identify what was unchecked, why, and the access or follow-up needed."),
]


def install_templates():
    data = catalogue()
    for service in data["services"]:
        code = "DD-" + service["service_code"]
        name = f"{code}-v{data['version']}"
        digest = hashlib.sha256(json.dumps(service, sort_keys=True).encode()).hexdigest()
        existing = frappe.db.exists("FP Questionnaire", name) or frappe.db.get_value("FP Questionnaire", {"questionnaire_code": code, "version": data["version"]}, "name")
        if existing:
            if frappe.db.get_value("FP Questionnaire", existing, "schema_hash") != digest:
                frappe.throw("Questionnaire source changed: publish a new version instead of overwriting " + name)
            continue
        doc = frappe.get_doc(dict(doctype="FP Questionnaire", questionnaire_code=code,
            title=service["title"], service_code=service["service_code"], version=data["version"],
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
    if found.intersection({"adult_enrolment", "university_fees", "adult_attendance", "adult_clinic"}) and not re.search(r"\badult\b|\buniversity\b|\bcollege\b", text): return None
    if len(found) == 1: return next(iter(found))
    if not found and request_type == "Construction Progress": return "construction"
    if not found and request_type == "General Site Visit": return "general_visit"
    return None


def prepare_project(doc, method=None):
    if not doc.get("scout_service"):
        doc.scout_service = infer_service(doc.get("project_title"), "") or infer_service((doc.get("project_title") or "") + " " + (doc.get("field_brief") or ""), doc.get("request_type"))
    if not doc.get("scout_service"): return
    services = catalogue()["services"]
    service = next((row for row in services if doc.scout_service in (row["service_code"], row["title"])), None)
    if not service: frappe.throw("Choose a service from the revised questionnaire library")
    code = service["service_code"]
    doc.scout_service = service["title"]
    name = frappe.db.get_value("FP Questionnaire", {"service_code": code, "status": "Published"}, "name", order_by="version desc")
    if not name: frappe.throw("Publish the service questionnaire before dispatch")
    previous_template = doc.get("scout_questionnaire")
    # Do not switch an existing project's pinned version just because a newer one was published.
    if previous_template and frappe.db.get_value("FP Questionnaire", previous_template, "service_code") == code and frappe.db.get_value("FP Questionnaire", previous_template, "status") == "Published":
        name = previous_template
    questions = frappe.get_all("FP Question", filters={"questionnaire": name, "active": 1}, fields=["name", "question_code", "validation_json"])
    service_rows = [q for q in questions if json.loads(q.validation_json or "{}").get("group") == "service"]
    if previous_template != name or not doc.get("scout_checks"):
        doc.scout_checks_confirmed = 0
        doc.set("scout_checks", [{"question": q.name} for q in service_rows])
    selected = [row.question for row in doc.get("scout_checks") or []]
    allowed = {q.name for q in service_rows}
    mandatory = {q.name for q in service_rows if json.loads(q.validation_json or "{}").get("mandatory_evidence")}
    if len(selected) != len(set(selected)) or not set(selected) <= allowed or not mandatory <= set(selected):
        frappe.throw("Select unique questions from this service and retain its mandatory photo/video question")
    previous = doc.get_doc_before_save() if not doc.is_new() else None
    if previous and previous.get("scout_checks_confirmed") and previous.get("scout_checks_confirmed") == doc.get("scout_checks_confirmed"):
        old = {row.question for row in previous.get("scout_checks") or []}
        if old != set(selected) or previous.get("scout_service") != doc.scout_service:
            doc.scout_checks_confirmed = 0
    doc.scout_questionnaire = name


def apply_to_task(doc, method=None):
    if not doc.is_new(): return
    if not doc.get("field_request"): return
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
    selected = {row.question for row in project.get("scout_checks") or []}
    questions = frappe.get_all("FP Question", filters={"questionnaire": doc.questionnaire, "active": 1}, fields=["name", "question_code", "validation_json"])
    doc.questionnaire_scope = json.dumps([q.question_code for q in questions if q.name in selected or json.loads(q.validation_json or "{}").get("group") in {"shared", "final"}])
    snapshot = {"task_scope": project.field_brief, "service": project.scout_service, "site_or_item": project.get("project_title"), "evidence_tasks": project.get("evidence_requirements")}
    if project.get("diaspora_request"):
        source = frappe.get_doc("Diaspora Request", project.diaspora_request)
        snapshot["client_request"] = source.original_brief
        rounds = frappe.get_all("DD Request Details", filters={"request": source.name, "status": ["in", ["Ready for review", "Closed"]]}, pluck="name", order_by="creation asc")
        snapshot["clarifications"] = [{"question": q.question, "answer": q.answer} for name in rounds for q in frappe.get_doc("DD Request Details", name).questions]
    doc.client_request_snapshot = json.dumps(snapshot)
