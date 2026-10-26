import frappe
from frappe.model.document import Document

from fieldpulse.utils import haversine_distance_m
from fieldpulse.geofence import effective_geofence_radius


class FPTaskResponse(Document):
    def validate(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        if self.is_new() and self.get('rework_of') and frappe.flags.dd_rework_response_uuid != self.client_uuid:
            frappe.throw('Only the coordinator rework action may create a revision')
        if previous:
            for key in ('rework_of', 'rework_type', 'rework_questions_json'):
                if self.get(key) != previous.get(key): frappe.throw('Rework provenance cannot be changed')
        if previous and previous.status == "Submitted":
            for key in ("task", "agent", "location", "status", "arrival_check_json", "final_review_json", "latitude", "longitude", "accuracy_m", "submitted_at", "started_at", "client_uuid", "device_id", "app_version", "client_updated_at", "geofence_status", "geofence_distance_m", "rejection_reason"):
                if self.get(key) != previous.get(key):
                    frappe.throw("Submitted scout findings are immutable; request rework for a new response")
            for key in ("qa_status", "review_status", "review_reasons", "reviewed_by", "reviewed_at", "review_notes"):
                if self.get(key) != previous.get(key):
                    frappe.throw("Use the coordinator review actions to record a review")
            return
        if "Field Agent" in frappe.get_roles() and not {"System Manager", "Field Operations Coordinator", "Supervisor", "Admin"}.intersection(frappe.get_roles()):
            task = frappe.get_doc("Field Task", self.task)
            scout = frappe.db.exists("Scout Profile", {"user": frappe.session.user})
            if not scout or self.agent != scout or task.scout_profile != scout:
                frappe.throw("Not your assigned task", frappe.PermissionError)
            if self.get("qa_status") not in (None, "", "Pending", previous.get("qa_status") if previous else "Pending") or self.get("reviewed_by") or self.get("review_notes"):
                frappe.throw("Only coordinators can review submissions", frappe.PermissionError)
        if self.is_new() and frappe.db.get_value("Field Task", self.task, "status") in ("Submitted", "Approved", "Cancelled", "Awaiting authorization"):
            frappe.throw("This task is no longer open for new responses")
        if frappe.db.get_value('Field Task', self.task, 'status') == 'Awaiting authorization':
            frappe.throw('This revisit is awaiting authorization')
        self._apply_geofence_check()
        from fieldpulse.scout_submissions import validate_submission
        managed = validate_submission(self)
        if self.status == "Submitted" and not managed:
            self._validate_submission_complete()
        self._sync_task_status()

    def _apply_geofence_check(self):
        if not self.location or self.latitude is None or self.longitude is None:
            self.geofence_status = "Invalid GPS"
            return
        location = frappe.get_doc("FP Location", self.location)
        distance = haversine_distance_m(
            self.latitude, self.longitude, location.latitude, location.longitude
        )
        self.geofence_distance_m = distance
        self.geofence_status = "Inside" if distance <= effective_geofence_radius(location.geofence_radius_m) else "Outside"


    def _validate_submission_complete(self):
        if self.geofence_status in ("Outside", "Invalid GPS"):
            frappe.throw(f"Cannot submit: location check failed ({self.geofence_status}).")

        if not self.task:
            return
        questionnaire = frappe.db.get_value("Field Task", self.task, "questionnaire")
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

        scope_raw = frappe.db.get_value('Field Task',self.task,'questionnaire_scope')
        scope = frappe.parse_json(scope_raw) if scope_raw else None
        for q in questions:
            if scope is not None and q['question_code'] not in scope:
                continue
            if not self._is_question_visible(q, answered_by_code) or not q['required'] and q['name'] not in answered_by_question:
                continue
            self._require_answer(q, answered_by_question)

    def _require_answer(self, q, answered_by_question):
        answer = answered_by_question.get(q["name"])
        from fieldpulse.legacy_questionnaires import answer_issue
        value = None
        if answer:
            raw = answer.get('answer_json')
            if raw is not None and raw != '':
                try:
                    value = frappe.parse_json(raw) if isinstance(raw,str) else raw
                except Exception:
                    frappe.throw(f"Invalid answer format: {q['label']}")
            else:
                value = answer.get('answer_text')
        options = ()
        if q['question_type'] in ('single_select','multi_select','rating_scale','yes_no'):
            rows = frappe.get_all('FP Question Option',filters={'question':q['name']},fields=['name','option_code','label'])
            options = tuple(row.get('option_code') or row.get('label') or row['name'] for row in rows)
        issue = answer_issue(q['question_type'],value,bool(q['required']),options)
        if issue:
            frappe.throw(f"{q['label']}: {issue}")
        if not answer or value is None or value == '' or value == []:
            return

        if q["question_type"] in ("photo", "file_attachment", "signature"):
            has_attachment = frappe.db.exists(
                "Field Evidence",
                {
                    "field_task": self.task,
                    "question_response": answer["name"],
                    "upload_status": "Uploaded",
                    "evidence_type": {'photo':'Photo','file_attachment':'Document','signature':'Signature'}[q['question_type']],
                },
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
        raw = target_answer.get('answer_json')
        if raw is not None and raw != '':
            try:
                actual = frappe.parse_json(raw) if isinstance(raw,str) else raw
            except Exception:
                return False
        else:
            actual = target_answer.get('answer_text')
        expected = rule.get('equals')
        if isinstance(actual,bool) or isinstance(expected,bool):
            return type(actual) is type(expected) and actual == expected
        return actual == expected

    def _sync_task_status(self):
        # Pre-creating a blank replacement revision must not mark the new scout
        # as having accepted or started fieldwork.
        if self.status == 'Draft' and frappe.flags.dd_rework_response_uuid == self.client_uuid:
            return
        if not self.task:
            return
        task = frappe.get_doc("Field Task", self.task)

        # A first saved response is an implicit acceptance/start for legacy
        # clients that save a draft before calling the explicit accept action.
        if self.status == "Draft":
            if task.status == "Assigned":
                task = self._transition_field_task(task, "Accepted")
            if task.status == "Accepted":
                self._transition_field_task(task, "In Progress")
            return

        if self.status != "Submitted" or task.status in ("Submitted", "Approved", "Rejected"):
            return
        if task.status == "Assigned":
            task = self._transition_field_task(task, "Accepted")
        if task.status == "Accepted":
            task = self._transition_field_task(task, "In Progress")
        if task.status != "In Progress":
            frappe.throw(f"Cannot submit Field Task while it is {task.status}")
        self._transition_field_task(task, "Submitted")

    @staticmethod
    def _transition_field_task(task, status):
        """Persist through Field Task hooks so derived state remains current."""
        task.status = status
        task.save(ignore_permissions=True)
        return frappe.get_doc("Field Task", task.name)
