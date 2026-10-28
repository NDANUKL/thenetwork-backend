"""Unit-test approval/version invariants without a running Frappe site."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


class Document:
    def __init__(self, **values):
        self.__dict__.update(values)

    def is_new(self):
        return self.previous is None

    def get_doc_before_save(self):
        return self.previous


class BriefVersionTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.get_roles.return_value = ['Field Operations Coordinator']
        self.frappe.PermissionError = PermissionError
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.dispatched = False
        self.frappe.db.get_value.side_effect = lambda doctype, *args, **kwargs: ('TASK-1' if self.dispatched else None) if doctype == 'Field Task' else 2
        self.frappe.session.user = 'coordinator@example.test'
        self.frappe.utils.now_datetime.return_value = '2026-10-28 12:00:00'
        self.frappe.whitelist.return_value = lambda function: function
        docmodule = types.ModuleType('frappe.model.document')
        docmodule.Document = Document
        spec = importlib.util.spec_from_file_location('task_brief_controller', ROOT / 'fieldpulse/fieldpulse/doctype/dd_task_brief/dd_task_brief.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.frappe, 'frappe.model.document': docmodule}):
            guard_spec = importlib.util.spec_from_file_location('fieldpulse.task_brief_revision_guard', ROOT / 'fieldpulse/task_brief_revision_guard.py')
            guard = importlib.util.module_from_spec(guard_spec)
            guard_spec.loader.exec_module(guard)
            guard_patch = patch.dict(sys.modules, {'fieldpulse.task_brief_revision_guard': guard})
            guard_patch.start()
            self.addCleanup(guard_patch.stop)
            spec.loader.exec_module(self.module)
        self.content = json.loads((ROOT / 'tests/fixtures/task-brief-v1.json').read_text())['brief']

    def doc(self, **changes):
        values = dict(previous=None, project='PROJECT-1', version=99, status='Draft', supersedes=None, content_json=json.dumps(self.content))
        return self.module.DDTaskBrief(**dict(values, **changes))

    def test_new_versions_are_server_allocated_under_project_lock(self):
        doc = self.doc()
        doc.validate()
        self.assertEqual(doc.version, 3)
        self.frappe.db.sql.assert_called_once()
        self.frappe.get_doc.return_value.check_permission.assert_called_with('write')
        self.assertEqual(len(doc.content_hash), 64)
        self.assertIsNone(doc.approved_by)

    def test_approval_is_stamped_by_server(self):
        doc = self.doc(status='Approved', approved_by='forged')
        doc.validate()
        self.assertEqual(doc.approved_by, 'coordinator@example.test')
        self.assertEqual(doc.approved_at, '2026-10-28 12:00:00')

    def test_flagged_requests_cannot_be_approved(self):
        self.content.update(review_required=True, review_reasons=['Scope unclear'])
        with self.assertRaisesRegex(ValueError, 'Task Brief needs review: Scope unclear'):
            self.doc(status='Approved').validate()

    def test_empty_checks_explain_how_to_complete_draft(self):
        self.content.update(checks=[], review_required=False, review_reasons=[])
        with self.assertRaisesRegex(ValueError, 'no field checks'):
            self.doc(status='Approved').validate()

    def test_approved_content_cannot_be_edited_or_deleted(self):
        previous = self.doc(status='Approved')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.doc(previous=previous).validate()
        with self.assertRaisesRegex(ValueError, 'retained for audit'):
            previous.on_trash()

    def test_scout_cannot_approve(self):
        self.frappe.get_roles.return_value = ['Ground Scout']
        with self.assertRaisesRegex(ValueError, 'Only coordinators'):
            self.doc(status='Approved').validate()

    def test_revision_must_reference_same_project(self):
        self.frappe.get_doc.return_value = MagicMock(project='OTHER', status='Approved', version=1)
        with self.assertRaisesRegex(ValueError, 'earlier approved brief'):
            self.doc(supersedes='BRIEF-1').validate()

    def test_dispatched_project_blocks_new_draft_and_direct_approval(self):
        self.dispatched = True
        for status in ('Draft', 'Approved'):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'started offline'):
                self.doc(status=status).validate()
        self.frappe.db.get_value.assert_called_with('Field Task', {
            'field_request': 'PROJECT-1', 'task_brief_version': ['is', 'set'],
        }, 'name', for_update=True)

    def test_draft_created_before_dispatch_cannot_be_edited_or_approved_afterwards(self):
        previous = self.doc(version=2)
        self.dispatched = True
        for status in ('Draft', 'Approved'):
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'assigned Task Brief'):
                self.doc(previous=previous, version=2, status=status).validate()


if __name__ == '__main__':
    unittest.main()
