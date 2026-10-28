from frappe.model.document import Document


class FieldRequest(Document):
    """Operational request awaiting allocation to a scout."""

    def after_insert(self):
        from fieldpulse.task_brief_workflow import seed_project_brief
        seed_project_brief(self)

    def onload(self):
        from fieldpulse.project_locations import sync_contact_access
        sync_contact_access(self)
