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

    # Use Frappe's copy_doc for a reliable deep copy
    new_doc = frappe.copy_doc(source, ignore_no_copy=False)
    new_doc.status = "Draft"

    # Safely increment the version number
    current_version = source.version or 0
    new_doc.version = current_version + 1

    # Clear linking fields from the original document
    new_doc.amended_from = source.name
    new_doc.name = None  # Let Frappe generate a new name

    new_doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return {"new_questionnaire": new_doc.name, "version": new_doc.version}
