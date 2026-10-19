"""Coordinator-authored reports; generated drafts never publish automatically."""
import hashlib
import json
from pathlib import Path
import frappe
from fieldpulse.scout_submissions import require_reviewer, submission_detail


def report_content_hash(doc):
    values = {key: doc.get(key) for key in ("request", "title", "executive_summary", "findings", "limitations", "next_steps", "review_sources_json", "report_version")}
    values["evidence"] = [{key: row.get(key) for key in ("evidence", "caption", "include_client")} for row in doc.get("report_evidence") or []]
    values["evidence_selection_reviewed"] = doc.get("evidence_selection_reviewed")
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


@frappe.whitelist(methods=["POST"])
def prepare_report(reference):
    require_reviewer()
    frappe.db.sql("SELECT name FROM `tabDiaspora Request` WHERE name=%s FOR UPDATE", [reference])
    request = frappe.get_doc("Diaspora Request", reference)
    if request.status != "Completed": frappe.throw("Review all scout work before preparing the client report")
    existing = frappe.db.get_value("DD Service Report", {"request": reference, "status": ["!=", "Approved"]}, "name", order_by="creation desc")
    if existing: return {"report": existing}
    projects = frappe.get_all("Field Request", filters={"diaspora_request": reference, "status": ["!=", "Cancelled"]}, pluck="name")
    tasks = frappe.get_all("Field Task", filters={"field_request": ["in", projects], "status": ["!=", "Cancelled"]}, fields=["name", "status"])
    if not tasks or any(task.status != "Approved" for task in tasks): frappe.throw("All active scout tasks must be approved")
    sources, findings, limitations, media = [], [], [], []
    for task in tasks:
        response = frappe.db.get_value("FP Task Response", {"task": task.name, "status": "Submitted", "qa_status": "Passed"}, "name", order_by="creation desc")
        if not response: frappe.throw("A scout task is missing its coordinator review")
        detail = submission_detail(response)
        sources.append({"task": task.name, "response": response})
        media.extend({"evidence": row.name, "evidence_type": row.evidence_type, "caption": row.caption, "include_client": 0} for row in detail["evidence"] if row.evidence_type in {"Photo", "Video"})
        questions = {q.name: q for q in detail["questions"]}
        for row in detail["answers"]:
            answer = frappe.parse_json(row.answer_json or "{}")
            if not isinstance(answer, dict): continue
            question = questions.get(row.question)
            if not question: continue
            text = answer.get("text") or ""
            details = [f"{answer.get('result', '')}: {text}"]
            for key, label in [("source", "Attributed source and statement"), ("concern_details", "Concern and location"), ("demonstration", "Demonstration")]:
                if answer.get(key): details.append(label + ": " + answer[key])
            findings.append(f"{task.name} / {question.question_code}: {question.label}\n" + "\n".join(details))
            if answer.get("media_unavailable_reason"): limitations.append(f"{task.name} / {question.question_code}: {answer['media_unavailable_reason']}")
            if answer.get("explanation"): limitations.append(f"{task.name} / {question.question_code}: {answer['explanation']}")
        review = detail["final_review"]
        if review.get("additional_text"): findings.append(f"{task.name} - Additional findings: {review['additional_text']}")
        if detail["review_reasons"]: limitations.append(task.name + ": " + detail["review_reasons"])
    version = frappe.db.count("DD Service Report", {"request": reference}) + 1
    doc = frappe.get_doc(dict(doctype="DD Service Report", request=reference, status="Draft", title="Verification report - " + reference,
        report_version=version, executive_summary="", findings="\n\n".join(findings), limitations="\n\n".join(limitations),
        review_sources_json=json.dumps(sources), report_evidence=media))
    doc.insert(ignore_permissions=True)
    return {"report": doc.name}


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
        parent = frappe.db.get_value("FP Question Response", evidence.question_response, "task_response")
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
    request = frappe.get_doc("Diaspora Request", doc.request)
    media = [{"caption": row.caption, "filename": evidence_archive_name(index, evidence)}
             for index, (row, evidence) in enumerate(selected_evidence(doc), 1)]
    html = frappe.render_template((Path(__file__).parent / "templates/reports/service_report.html").read_text(encoding="utf-8"), {"doc": doc, "request": request, "evidence": media})
    from frappe.utils.pdf import get_pdf
    from frappe.utils.file_manager import save_file
    pdf = get_pdf(html, options={"footer-right": "Page [page] of [topage]", "footer-font-size": "8", "footer-spacing": "6"})
    file = save_file(f"{doc.request}-report-v{doc.report_version or 1}.pdf", pdf, doc.doctype, doc.name, is_private=1)
    doc.report_file = file.file_url
    doc.generated_from_hash = report_content_hash(doc)
    doc.save()
    return {"report": doc.name, "file": file.file_url}


def evidence_archive_name(index, evidence):
    import re
    original = (evidence.original_filename or "evidence").replace("\\", "/").rsplit("/", 1)[-1]
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", original).strip(".")[:140] or "evidence"
    folder = "Photos" if evidence.evidence_type == "Photo" else "Videos"
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
