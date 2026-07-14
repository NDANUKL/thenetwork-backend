import frappe
from frappe.model.document import Document

from fieldpulse.utils import haversine_distance_m


class FPTaskResponse(Document):
    def validate(self):
        self._apply_geofence_check()
        if self.status == "Submitted":
            self._validate_submission_complete()
        self._sync_task_status()

    def _apply_geofence_check(self):
        if not (self.location and self.latitude and self.longitude):
            self.geofence_status = "Invalid GPS"
            return
        location = frappe.get_doc("FP Location", self.location)
        distance = haversine_distance_m(
            self.latitude, self.longitude, location.latitude, location.longitude
        )
        self.geofence_distance_m = distance
        self.geofence_status = "Inside" if distance <= (location.geofence_radius_m or 50) else "Outside"


    def _validate_submission_complete(self):
        if self.geofence_status in ("Outside", "Invalid GPS"):
            frappe.throw(f"Cannot submit: location check failed ({self.geofence_status}).")

        if not self.task:
            return
        questionnaire = frappe.db.get_value("FP Task", self.task, "questionnaire")
        if not questionnaire:
            return

        questions = frappe.get_all(
            "FP Question",
            filters={"questionnaire": questionnaire, "active": 1},
            fields=["name", "question_code", "label", "required", "question_type", "display_logic_json"],
        )
        answers = frappe.get_all(
            "FP Question Response",
            filters={"task_response": self.name},
            fields=["name", "question", "question_code", "answer_text", "answer_json"],
        )
        answered_by_question = {a["question"]: a for a in answers}
        answered_by_code = {a["question_code"]: a for a in answers}

        for q in questions:
            if not q["required"] or not self._is_question_visible(q, answered_by_code):
                continue
            self._require_answer(q, answered_by_question)

    def _require_answer(self, q, answered_by_question):
        answer = answered_by_question.get(q["name"])
        if not answer or (not answer.get("answer_text") and not answer.get("answer_json")):
            frappe.throw(f"Missing required answer: {q['label']}")

        if q["question_type"] in ("photo", "file_attachment", "signature"):
            has_attachment = frappe.db.exists(
                "FP Attachment", {"question_response": answer["name"]}
            ) or frappe.db.exists(
                "FP Attachment",
                {"task_response": self.name, "attachment_type": q["question_type"].split("_")[0].capitalize()},
            )
            if not has_attachment:
                frappe.throw(f"Missing required attachment for: {q['label']}")

    def _is_question_visible(self, question, answered_by_code):
        rule_raw = question.get("display_logic_json")
        if not rule_raw:
            return True
        try:
            rule = frappe.parse_json(rule_raw)
        except Exception:
            return True  # malformed rule shouldn't hard-block submission

        target_code = rule.get("question_code")
        if not target_code:
            return True
        target_answer = answered_by_code.get(target_code)
        if not target_answer:
            return False  # controlling question wasn't answered yet
        actual = target_answer.get("answer_text") or target_answer.get("answer_json")
        return str(actual) == str(rule.get("equals"))

    def _sync_task_status(self):
        if not self.task:
            return
        task_status = frappe.db.get_value("FP Task", self.task, "status")
        if self.status == "Submitted" and task_status not in ("Submitted", "Approved", "Rejected"):
            frappe.db.set_value("FP Task", self.task, "status", "Submitted")
        elif self.status == "Draft" and task_status == "Assigned":
            frappe.db.set_value("FP Task", self.task, "status", "In Progress")
