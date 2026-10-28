"""Coordinator-authored reports; generated drafts never publish automatically."""
import hashlib
import json
from pathlib import Path
import frappe
from fieldpulse.scout_submissions import require_reviewer, submission_detail


def prepare_if_ready(reference):
    projects = frappe.get_all('Field Request', filters={'diaspora_request': reference, 'status': ['!=', 'Cancelled']}, pluck='name')
    tasks = frappe.get_all('Field Task', filters={'field_request': ['in', projects], 'status': ['!=', 'Cancelled']}, fields=['name', 'status', 'task_brief_version']) if projects else []
    if not tasks or any(task.status != 'Approved' for task in tasks): return None
    if any(getattr(task, 'task_brief_version', None) for task in tasks):
        from fieldpulse.task_brief_workflow import coverage_ready
        if not coverage_ready(projects): return None
    return prepare_report(reference)['report']


def report_content_hash(doc):
    values = {key: doc.get(key) for key in ("request", "title", "executive_summary", "findings", "limitations", "next_steps", "review_sources_json", "report_version", "coverage_snapshot_json", "scope_snapshot_json", "visit_snapshot_json", "scope_coverage_reviewed", "review_signatory", "review_signed_at")}
    values["evidence"] = [{key: row.get(key) for key in ("evidence", "caption", "include_client")} for row in doc.get("report_evidence") or []]
    values["evidence_selection_reviewed"] = doc.get("evidence_selection_reviewed")
    values['checks'] = [{key: row.get(key) for key in ('check_id','project','task','customer_question','findings','assessment','basis','basis_detail','limitations','limitation_acknowledged','answer_refs_json','evidence_ids_json','recorded_gaps_json')} for row in doc.get('report_checks') or []]
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


@frappe.whitelist(methods=["POST"])
def prepare_report(reference):
    require_reviewer()
    frappe.db.sql("SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE", [reference])
    request = frappe.get_doc("Diaspora Request", reference)
    if request.status != "Completed": frappe.throw("Review all scout work before preparing the client report")
    existing = frappe.db.get_value("DD Service Report", {"request": reference, "status": ["!=", "Approved"]}, "name", order_by="creation desc")
    if existing: return {"report": existing}
    from fieldpulse.report_preparation import prepare_content
    content = prepare_content(reference)
    version = frappe.db.count("DD Service Report", {"request": reference}) + 1
    doc = frappe.get_doc(dict(doctype="DD Service Report", request=reference, status="Draft", title="Verification report - " + reference, report_version=version, **content))
    marker = frappe.flags.dd_preparing_report
    frappe.flags.dd_preparing_report = True
    try: doc.insert(ignore_permissions=True)
    finally: frappe.flags.dd_preparing_report = marker
    return {"report": doc.name}


@frappe.whitelist(methods=['POST'])
def refresh_draft(report):
    require_reviewer()
    reference = frappe.db.get_value('DD Service Report', report, 'request')
    frappe.db.sql('SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE', [reference])
    frappe.db.sql('SELECT name FROM `tabDD Service Report` WHERE name=%s FOR UPDATE', [report])
    doc = frappe.get_doc('DD Service Report', report)
    doc.check_permission('write')
    if doc.status == 'Approved': frappe.throw('Approved reports are locked; prepare a new version')
    from fieldpulse.report_preparation import prepare_content
    for key, value in prepare_content(reference).items(): doc.set(key, value)
    marker = frappe.flags.dd_preparing_report
    frappe.flags.dd_preparing_report = True
    try: doc.save()
    finally: frappe.flags.dd_preparing_report = marker
    return {'report': doc.name}



def selected_evidence(doc):
    result = []
    seen = set()
    for row in doc.get("report_evidence") or []:
        if not row.include_client: continue
        if row.evidence in seen: frappe.throw("Select each evidence record once")
        seen.add(row.evidence)
        evidence = frappe.get_doc("Field Evidence", row.evidence)
        task = frappe.get_doc("Field Task", evidence.field_task)
        reference = frappe.db.get_value("Field Request", task.field_request, "diaspora_request") if task.field_request else None
        if reference != doc.request or task.status != "Approved" or evidence.upload_status != "Uploaded" or evidence.evidence_type not in {"Photo", "Video"}:
            frappe.throw("Client evidence must come from this request's approved scout work")
        parent = evidence.get('task_response') or frappe.db.get_value("FP Question Response", evidence.question_response, "task_response")
        from fieldpulse.scout_lineage import evidence_origin_allowed
        approved_sources = [item.get('response') for item in json.loads(doc.get('review_sources_json') or '[]')]
        parent = next((source for source in approved_sources if source and evidence_origin_allowed(source, parent, frappe.get_doc)), parent)
        source_ids = {item.get("response") for item in json.loads(doc.get("review_sources_json") or "[]")}
        if (source_ids and parent not in source_ids) or not frappe.db.exists("FP Task Response", {"name": parent, "task": task.name, "qa_status": "Passed", "reviewed_by": ["is", "set"]}):
            frappe.throw("Evidence must belong to a coordinator-approved submission included in this report")
        row.evidence_type = evidence.evidence_type
        if not (row.caption or "").strip(): frappe.throw("Caption every client evidence item")
        result.append((row, evidence))
    return result


def evidence_bytes(evidence):
    from fieldpulse.evidence import _r2_client, _r2_settings, _normalise_etag
    settings = _r2_settings()
    if (evidence.file_size or 0) > 100000000: frappe.throw("Evidence is too large to include")
    stored = _r2_client(settings).get_object(Bucket=settings["bucket"], Key=evidence.r2_object_key)
    if _normalise_etag(stored.get("ETag")) != _normalise_etag(evidence.etag):
        frappe.throw("Evidence changed after verification; contact the coordinator")
    content = stored["Body"].read(100000001)
    if len(content) > 100000000 or len(content) != evidence.file_size: frappe.throw("Evidence size does not match its verified upload")
    return content


@frappe.whitelist()
def download_evidence(reference, evidence_id):
    from fieldpulse.payments import _owned
    _owned(reference)
    name = frappe.db.get_value("DD Service Report", {"request": reference, "status": "Approved"}, "name", order_by="creation desc")
    if not name: frappe.throw("An approved report is not available", frappe.PermissionError)
    doc = frappe.get_doc("DD Service Report", name)
    match = next((evidence for row, evidence in selected_evidence(doc) if row.name == evidence_id), None)
    if not match: frappe.throw("This evidence was not released with the approved report", frappe.PermissionError)
    frappe.response["type"] = "download"
    frappe.response["filename"] = match.original_filename
    frappe.response["content_type"] = match.mime_type
    frappe.response["filecontent"] = evidence_bytes(match)
    frappe.response["display_content_as"] = "attachment"


@frappe.whitelist(methods=["POST"])
def generate_pdf(report):
    require_reviewer()
    doc = frappe.get_doc("DD Service Report", report)
    doc.check_permission("write")
    if doc.status == "Approved": frappe.throw("Approved reports are locked; prepare a new version")
    if not (doc.get("executive_summary") or "").strip() or not (doc.get("findings") or "").strip():
        frappe.throw("Write the client summary and review the findings before generating the PDF")
    if not doc.get("evidence_selection_reviewed"):
        frappe.throw("Review the client evidence selection before generating the PDF")
    from fieldpulse.customer_coverage import validate_report
    validate_report(doc, approving=True)
    doc.review_signatory = frappe.session.user
    doc.review_signed_at = frappe.utils.now_datetime()
    request = frappe.get_doc("Diaspora Request", doc.request)
    selected = selected_evidence(doc)
    media = [{"caption": row.caption, "filename": evidence_archive_name(index, evidence)}
             for index, (row, evidence) in enumerate(selected, 1)]
    from fieldpulse.report_preparation import pdf_context
    report_context = pdf_context(doc, selected)
    html = frappe.render_template((Path(__file__).parent / "templates/reports/service_report.html").read_text(encoding="utf-8"), {"doc": doc, "request": request, "evidence": media, **report_context})
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import save_file
    pdf = get_pdf(html, options={"footer-right": "Page [page] of [topage]", "footer-font-size": "8", "footer-spacing": "6"})
    file = save_file(f"{doc.request}-report-v{doc.report_version or 1}.pdf", pdf, doc.doctype, doc.name, is_private=1)
    doc.report_file = file.file_url
    doc.generated_from_hash = report_content_hash(doc)
    marker = frappe.flags.dd_preparing_report
    frappe.flags.dd_preparing_report = True
    try: doc.save()
    finally: frappe.flags.dd_preparing_report = marker
    return {"report": doc.name, "file": file.file_url}


def evidence_archive_name(index, evidence):
    import re
    original = (evidence.original_filename or "evidence").replace("\\", "/").rsplit("/", 1)[-1]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", original).strip(".")[:140] or "evidence"
    folder = {"Photo":"Photos", "Video":"Videos", "Document":"Documents"}.get(evidence.evidence_type, 'Documents')
    return f"{folder}/{index:03d}-{safe}"


def build_report_bundle(doc, pdf):
    """Package only coordinator-selected, verified media alongside the private PDF."""
    from io import BytesIO
    from zipfile import ZipFile, ZIP_STORED
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF-"):
        frappe.throw("The approved report PDF is unavailable")
    selected = selected_evidence(doc)
    if len(pdf) + sum(evidence.file_size or 0 for _, evidence in selected) > 500000000:
        frappe.throw("Report download exceeds 500 MB; ask the coordinator to reduce the selected evidence")
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_STORED) as archive:
        archive.writestr("report.pdf", pdf)
        for index, (_, evidence) in enumerate(selected, 1):
            archive.writestr(evidence_archive_name(index, evidence), evidence_bytes(evidence))
    return output.getvalue()
