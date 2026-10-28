import frappe
from frappe.model.document import Document


class FieldEvidence(Document):
    def validate(self):
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and previous.get('task_response'):
            for key in ('field_task', 'scout', 'task_response', 'field_check_id', 'client_uuid',
                        'evidence_type', 'captured_at', 'gps_lat', 'gps_lng', 'accuracy_m',
                        'location_sampled_at', 'metadata_origin', 'r2_object_key', 'file_size', 'mime_type'):
                if self.get(key) != previous.get(key):
                    frappe.throw('Original Task Brief evidence identity and capture metadata cannot be changed')
