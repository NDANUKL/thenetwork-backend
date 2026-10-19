import frappe
from frappe.model.document import Document

class FPQuestionResponse(Document):
    def validate(self):
        parent = frappe.get_doc("FP Task Response", self.task_response)
        task = frappe.get_doc("Field Task", parent.task)
        question = frappe.get_doc("FP Question", self.question)
        if parent.status != "Draft":
            frappe.throw("Submitted answers are immutable; request rework")
        if question.questionnaire != task.questionnaire or question.question_type != self.question_type:
            frappe.throw("Question is not part of the assigned questionnaire")
        scope = task.get("questionnaire_scope")
        if scope and question.question_code not in frappe.parse_json(scope):
            frappe.throw("Question was not selected before dispatch")
        self.question_code = question.question_code
        if "Field Agent" in frappe.get_roles() and not {"System Manager", "Field Operations Coordinator", "Supervisor", "Admin"}.intersection(frappe.get_roles()):
            scout = frappe.db.exists("Scout Profile", {"user": frappe.session.user})
            if not scout or parent.agent != scout or task.scout_profile != scout:
                frappe.throw("Not your assigned response", frappe.PermissionError)
