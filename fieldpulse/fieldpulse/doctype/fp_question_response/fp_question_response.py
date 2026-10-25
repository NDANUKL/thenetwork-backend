import frappe
from frappe.model.document import Document

class FPQuestionResponse(Document):
    def validate(self):
        parent = frappe.get_doc("FP Task Response", self.task_response)
        task = frappe.get_doc("Field Task", parent.task)
        if task.status == 'Awaiting authorization': frappe.throw('This revisit is awaiting authorization')
        from fieldpulse.scout_visit import require_verified_arrival
        require_verified_arrival(parent, task)
        question = frappe.get_doc("FP Question", self.question)
        if parent.status != "Draft":
            frappe.throw("Submitted answers are immutable; request rework")
        if question.questionnaire != task.questionnaire or question.question_type != self.question_type:
            frappe.throw("Question is not part of the assigned questionnaire")
        scope = task.get("questionnaire_scope")
        if scope and question.question_code not in frappe.parse_json(scope):
            frappe.throw("Question was not selected before dispatch")
        self.question_code = question.question_code
        if self.get('evidence_links'):
            from fieldpulse.scout_v2 import task_questions
            from fieldpulse.scout_library import decode, required_evidence
            pinned = next((row for row in task_questions(task, []) if row['name'] == self.question), None)
            if not pinned: frappe.throw('Evidence links require a pinned version 2 question')
            rules = {r['requirement_id']:r for r in required_evidence(self.question_code, decode(pinned['validation_json']), decode(self.answer_json, {}))}
            seen = set()
            for link in self.evidence_links:
                evidence = frappe.get_doc('Field Evidence', link.evidence)
                origin_response = frappe.db.get_value('FP Question Response', evidence.question_response, 'task_response')
                rule = rules.get(link.requirement_id)
                identity = (link.evidence, link.requirement_id)
                if not rule or identity in seen or not str(link.support_note or '').strip(): frappe.throw('Invalid or duplicate evidence requirement link')
                from fieldpulse.scout_lineage import evidence_origin_allowed
                if evidence.field_task != task.name or not evidence_origin_allowed(parent.name, origin_response, frappe.get_doc) or evidence.scout != parent.agent or evidence.upload_status != 'Uploaded' or evidence.evidence_type != rule['kind']:
                    frappe.throw('Evidence must be a verified matching file from this response', frappe.PermissionError)
                seen.add(identity)
        if "Field Agent" in frappe.get_roles() and not {"System Manager", "Field Operations Coordinator", "Supervisor", "Admin"}.intersection(frappe.get_roles()):
            scout = frappe.db.exists("Scout Profile", {"user": frappe.session.user})
            if not scout or parent.agent != scout or task.scout_profile != scout:
                frappe.throw("Not your assigned response", frappe.PermissionError)
