from frappe.model.document import Document


class ScoutApplication(Document):
    def validate(self):
        from fieldpulse.scout_access import validate_application
        validate_application(self)

    def on_trash(self):
        from fieldpulse.scout_access import prevent_application_deletion
        prevent_application_deletion(self)
