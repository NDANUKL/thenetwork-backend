import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from tests.test_native_integration import load


class RejectedAssignmentGuardTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.throw.side_effect = lambda message, exc=None: (_ for _ in ()).throw((exc or ValueError)(message))
        self.frappe.db.get_value.side_effect = lambda doctype, filters, field=None, **kw: (
            'REJECTED-TASK' if doctype == 'Field Task' and filters.get('submission_review_status') == 'Reject' else
            'Active' if field == 'access_status' else
            'Available' if field == 'availability_status' else None
        )
        self.module = load('field_task_rejection_guard_test', 'fieldpulse/fieldpulse/doctype/field_task/field_task.py', {
            'frappe': self.frappe,
            'frappe.model.document': types.SimpleNamespace(Document=type('Document', (), {})),
            'frappe.utils': types.SimpleNamespace(now_datetime=lambda: '2026-10-31 10:00:00'),
            'fieldpulse.fieldpulse.doctype.scout_profile.scout_profile': types.SimpleNamespace(
                recalculate_workload_and_availability=lambda scout: None),
        })

    def test_document_validation_rejects_reassignment_to_rejected_scout(self):
        task = types.SimpleNamespace(field_request='PROJECT', scout_profile='SCOUT', get=lambda key: {'field_request':'PROJECT'}.get(key), is_new=lambda: True)
        with self.assertRaisesRegex(ValueError, 'rejected for this project'):
            self.module.FieldTask._validate_scout_assignment(task, None)
        self.frappe.db.sql.assert_any_call(
            'SELECT name FROM `tabField Request` WHERE name=%s FOR UPDATE', ('PROJECT',))

    def test_document_validation_allows_scout_without_rejection_record(self):
        self.frappe.db.get_value.side_effect = lambda doctype, filters, field=None, **kw: (
            'Active' if field == 'access_status' else 'Available' if field == 'availability_status' else None)
        task = types.SimpleNamespace(field_request='PROJECT', scout_profile='SCOUT', get=lambda key: {'field_request':'PROJECT'}.get(key), is_new=lambda: True)
        self.module.FieldTask._validate_scout_assignment(task, None)
        self.frappe.db.sql.assert_any_call(
            'SELECT name FROM `tabScout Profile` WHERE name=%s FOR UPDATE', ('SCOUT',))


if __name__ == '__main__':
    unittest.main()
