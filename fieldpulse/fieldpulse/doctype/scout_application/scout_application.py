from frappe.model.document import Document


class ScoutApplication(Document):
    def after_insert(self):
        from fieldpulse.coordinator_notifications import application_received
        application_received(self)

    def validate(self):
        from fieldpulse.scout_access import validate_application
        validate_application(self)

    def on_trash(self):
        from fieldpulse.scout_access import prevent_application_deletion
        prevent_application_deletion(self)
