import frappe
from frappe.model.document import Document

class FPQuestionnaire(Document):
    def validate(self):
        if self.get("service_code") and self.status == "Published":
            import json
            from fieldpulse.scout_templates import SHARED
            rows = frappe.get_all("FP Question", filters={"questionnaire": self.name, "active": 1}, fields=["question_code", "question_type", "required", "validation_json"])
            codes = [row.question_code for row in rows]
            if rows and all(json.loads(row.validation_json or '{}').get('protocol_version') == 2 for row in rows):
                from fieldpulse.scout_library import validate_config
                from fieldpulse.scout_library import SHARED_V2
                if len(codes) != len(set(codes)) or not {'S1', 'S2', 'S_EXTRA'}.issubset(codes) or {'S3', 'S4'}.intersection(codes):
                    frappe.throw('Version 2 requires two unique opening questions and one optional closing question')
                for row in rows:
                    config = json.loads(row.validation_json)
                    try: validate_config(config)
                    except ValueError as error: frappe.throw(str(error))
                    expected = next((shared for shared in SHARED_V2 if shared['code'] == row.question_code), None)
                    if row.question_type != 'service_check' or config.get('group') not in {'shared','service','final'}: frappe.throw('Use structured version 2 service questions')
                    if expected and (config.get('group') != 'shared' or config.get('result_options') != expected['result_options']): frappe.throw('Keep the version 2 opening outcomes')
                    if row.question_code == 'S_EXTRA' and (config.get('group') != 'final' or not config.get('optional') or row.required): frappe.throw('The closing question must remain optional')
                self._validate_published_identity()
                return
            if len(codes) != len(set(codes)) or not {"S1", "S2", "S3", "S4", "S_EXTRA"}.issubset(codes):
                frappe.throw("Retain unique shared visit questions and the final additional-evidence question")
            mandatory = 0
            expected = {code: options for code, label, options, detail in SHARED}
            for row in rows:
                config = json.loads(row.validation_json or "{}")
                if row.question_type != "service_check" or config.get("group") not in {"shared", "service", "final"}:
                    frappe.throw("Managed service templates require structured service checks")
                if row.question_code in expected and (config.get("group") != "shared" or config.get("result_options") != expected[row.question_code]):
                    frappe.throw("Keep the shared response values used by the visit protocol")
                if config.get("group") != "final" and not row.required:
                    frappe.throw("Every displayed service check must require an answer")
                if config.get("group") == "service" and config.get("mandatory_evidence"): mandatory += 1
            if mandatory != 1: frappe.throw("Retain exactly one mandatory photo-and-video service question")
        self._validate_published_identity()
        if not self.is_new():
            old_status = frappe.db.get_value("FP Questionnaire", self.name, "status")
            if old_status == "Published" and self.status == "Published":
                self._block_content_edits_once_published()

    def _validate_published_identity(self):
        if not self.is_new() and self.get("service_code"):
            old = self.get_doc_before_save()
            if old and old.get("published_at"):
                for key in ("title", "description", "version", "service_code", "questionnaire_code", "source_sha256", "schema_hash", "project", "base_questionnaire"):
                    if self.get(key) != old.get(key):
                        frappe.throw("Published service templates are immutable; create a new version")

    def _block_content_edits_once_published(self):
        old = frappe.get_doc("FP Questionnaire", self.name)
        for field in ("title", "description"):
            if self.get(field) != old.get(field):
                frappe.throw(
                    "This questionnaire is Published and locked. "
                    "Use 'Create New Version' instead of editing it directly."
                )


@frappe.whitelist(methods=["POST"])
def create_new_version(questionnaire_code):
    """Clone the latest version of a questionnaire (with its questions
    and options) into a new Draft version, so existing task submissions
    keep referencing the exact version they were shown."""
    if not frappe.has_permission("FP Questionnaire", "create"):
        frappe.throw("Not permitted to create questionnaire versions", frappe.PermissionError)
    versions = frappe.get_all(
        "FP Questionnaire",
        filters={"questionnaire_code": questionnaire_code},
        fields=["name", "version"],
        order_by="version desc",
        limit=1,
    )
    if not versions:
        frappe.throw(f"No questionnaire found with code {questionnaire_code}")

    latest = versions[0]
    source = frappe.get_doc("FP Questionnaire", latest["name"])

    # Use Frappe's copy_doc for a reliable deep copy
    new_doc = frappe.copy_doc(source, ignore_no_copy=False)
    new_doc.status = "Draft"

    # Safely increment the version number
    current_version = source.version or 0
    new_doc.version = current_version + 1

    # Clear linking fields from the original document
    new_doc.amended_from = source.name
    new_doc.name = None  # Let Frappe generate a new name

    new_doc.published_at = None
    new_doc.insert(ignore_permissions=True)
    for row in frappe.get_all("FP Question", filters={"questionnaire": source.name}, pluck="name"):
        question = frappe.copy_doc(frappe.get_doc("FP Question", row))
        question.name = None
        question.client_uuid = None
        question.questionnaire = new_doc.name
        question.insert(ignore_permissions=True)
        for option_name in frappe.get_all("FP Question Option", filters={"question": row}, pluck="name"):
            option = frappe.copy_doc(frappe.get_doc("FP Question Option", option_name))
            option.name = None
            option.question = question.name
            option.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"new_questionnaire": new_doc.name, "version": new_doc.version}
