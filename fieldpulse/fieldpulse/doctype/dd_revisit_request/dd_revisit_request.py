from frappe.model.document import Document


class DDRevisitRequest(Document):
    def validate(self):
        from fieldpulse.revisit_authorization import validate_document
        validate_document(self)
