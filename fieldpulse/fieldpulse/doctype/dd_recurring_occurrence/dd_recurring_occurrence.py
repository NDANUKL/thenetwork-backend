from frappe.model.document import Document

class DDRecurringOccurrence(Document):
    def validate(self):
        from fieldpulse.recurring import validate_document
        validate_document(self)
