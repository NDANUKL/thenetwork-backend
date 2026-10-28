"""Stored questionnaire submission readers; new work uses task_brief_workflow."""
import json
import frappe
from fieldpulse.scout_library import decode, required_evidence, visible


def task_questions(task, fallback):
    snapshot = decode(task.get('client_request_snapshot'), {})
    return snapshot.get('resolved_questions') or fallback


def linked_evidence(response, question_response):
    rows = []
    for link in frappe.get_all('DD Answer Evidence Link', filters={'parent': question_response, 'parenttype':'FP Question Response'}, fields=['evidence', 'requirement_id', 'support_note']):
        evidence = frappe.get_doc('Field Evidence', link.evidence)
        origin = frappe.get_doc('FP Question Response', evidence.question_response)
        from fieldpulse.scout_lineage import evidence_origin_allowed
        if not evidence_origin_allowed(response, origin.task_response, frappe.get_doc) or evidence.upload_status != 'Uploaded': frappe.throw('Evidence is outside this response or not verified')
        rows.append(frappe._dict(name=evidence.name, evidence_type=evidence.evidence_type, caption=evidence.caption,
            gps_lat=evidence.gps_lat, gps_lng=evidence.gps_lng, accuracy_m=evidence.accuracy_m,
            description=evidence.get('description'), clarification_required=evidence.get('clarification_required'),
            metadata_origin=evidence.get('metadata_origin'), location_sampled_at=evidence.get('location_sampled_at'),
            captured_at=evidence.captured_at, requirement_id=link.requirement_id, support_note=link.support_note,
            question_response=question_response))
    return rows
