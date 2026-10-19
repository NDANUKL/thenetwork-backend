import frappe
from frappe.model.document import Document


class FPQuestion(Document):
    def validate(self):
        parent = frappe.get_doc("FP Questionnaire", self.questionnaire)
        if parent.get("service_code") and parent.get("published_at"):
            frappe.throw("Published service questions are locked; create a new questionnaire version")

        if parent.get("service_code"):
            import json
            config = json.loads(self.validation_json) if self.validation_json else {"group": "service", "protocol_version": 1}
            self.validation_json = json.dumps(config)
            self.question_group = {"shared": "Shared", "service": "Service", "final": "Final review"}.get(config.get("group"))
            if config.get("group") != "final": self.required = 1

    def on_trash(self):
        self.validate()

