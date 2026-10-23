"""Questionnaire versions are assigned automatically and preserved on task updates."""
import types
import unittest
from unittest.mock import MagicMock
from tests.test_native_integration import load, fake_frappe


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value


class QuestionnaireVersionTests(unittest.TestCase):
    def setUp(self):
        self.api = fake_frappe()
        self.api.db.get_value.return_value = 3
        self.module = load('task_version_test', 'fieldpulse/fieldpulse/doctype/field_task/field_task.py', {
            'frappe': self.api,
            'frappe.model.document': types.SimpleNamespace(Document=object),
            'frappe.utils': types.SimpleNamespace(now_datetime=lambda: 'now'),
            'fieldpulse.fieldpulse.doctype.scout_profile.scout_profile': types.SimpleNamespace(recalculate_workload_and_availability=MagicMock()),
        })

    def validate(self, questionnaire, version, previous=None):
        doc = Record(questionnaire=questionnaire, questionnaire_version=version,
            is_new=lambda: previous is None, get_doc_before_save=lambda: previous,
            _validate_scout_assignment=MagicMock(), _apply_status_transition=MagicMock())
        self.module.FieldTask.validate(doc)
        return doc

    def test_new_task_uses_assigned_questionnaire_version(self):
        self.assertEqual(self.validate('Q-1', 999).questionnaire_version, 3)
        self.api.db.get_value.assert_called_once_with('FP Questionnaire', 'Q-1', 'version')

    def test_existing_task_preserves_original_version(self):
        previous = Record(questionnaire='Q-1', questionnaire_version=2)
        self.assertEqual(self.validate('Q-1', 999, previous).questionnaire_version, 2)
        self.api.db.get_value.assert_not_called()

    def test_task_without_questionnaire_has_no_version(self):
        self.assertEqual(self.validate(None, 999).questionnaire_version, 0)
        self.api.db.get_value.assert_not_called()
