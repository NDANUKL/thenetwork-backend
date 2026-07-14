import frappe
from frappe.model.document import Document


class FPQuestionnaire(Document):
    def validate(self):
        if not self.is_new():
            old_status = frappe.db.get_value("FP Questionnaire", self.name, "status")
            if old_status == "Published" and self.status == "Published":
                self._block_content_edits_once_published()

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

    new_doc = frappe.get_doc({
        "doctype": "FP Questionnaire",
        "questionnaire_code": questionnaire_code,
        "title": source.title,
        "version": (latest["version"] or 1) + 1,
        "status": "Draft",
        "description": source.description,
    })
    new_doc.insert(ignore_permissions=True)

    questions = frappe.get_all(
        "FP Question",
        filters={"questionnaire": source.name},
        fields=["*"],
        order_by="sequence asc",
    )
    for q in questions:
        new_q = frappe.get_doc({
            "doctype": "FP Question",
            "questionnaire": new_doc.name,
            "question_code": q["question_code"],
            "label": q["label"],
            "help_text": q["help_text"],
            "question_type": q["question_type"],
            "sequence": q["sequence"],
            "required": q["required"],
            "validation_json": q["validation_json"],
            "display_logic_json": q["display_logic_json"],
            "active": q["active"],
        })
        new_q.insert(ignore_permissions=True)

        options = frappe.get_all(
            "FP Question Option", filters={"question": q["name"]},
            fields=["*"], order_by="sequence asc",
        )
        for opt in options:
            frappe.get_doc({
                "doctype": "FP Question Option",
                "question": new_q.name,
                "option_code": opt["option_code"],
                "label": opt["label"],
                "sequence": opt["sequence"],
                "score": opt["score"],
                "active": opt["active"],
            }).insert(ignore_permissions=True)

    frappe.db.commit()
    return {"new_questionnaire": new_doc.name, "version": new_doc.version}
