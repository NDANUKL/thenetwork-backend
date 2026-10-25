from frappe.model.document import Document

class DDRecurringPlan(Document):
    def validate(self):
        from fieldpulse.recurring import validate_document
        validate_document(self)
