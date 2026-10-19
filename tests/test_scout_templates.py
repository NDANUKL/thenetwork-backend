import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def set(self, key, value): self[key] = [Record(row) for row in value] if isinstance(value, list) else value
    def is_new(self): return not self.get('name')
    def get_doc_before_save(self): return None


class FakeSite:
    def __init__(self):
        self.rows = {}
        self.db = types.SimpleNamespace(exists=self.exists, get_value=self.value)
        self.utils = types.SimpleNamespace(now_datetime=lambda: '2026-10-20 09:00:00')
    def throw(self, message): raise ValueError(message)
    def matching(self, dt, filters=None):
        rows = [row for (kind, name), row in self.rows.items() if kind == dt]
        if isinstance(filters, str): return [row for row in rows if row.name == filters]
        return [row for row in rows if all(row.get(k) == v for k, v in (filters or {}).items())]
    def exists(self, dt, filters):
        rows = self.matching(dt, filters)
        return rows[0].name if rows else None
    def value(self, dt, filters, field, **kwargs):
        rows = self.matching(dt, filters)
        rows.sort(key=lambda row: row.get('version') or 0, reverse=True)
        return rows[0].get(field) if rows else None
    def get_all(self, dt, filters=None, pluck=None, **kwargs):
        rows = self.matching(dt, filters)
        return [row.get(pluck) for row in rows] if pluck else rows
    def get_doc(self, dt, name=None):
        if isinstance(dt, str): return self.rows[(dt, name)]
        doc = Record(dt)
        def save(**kwargs):
            self.rows[(doc.doctype, doc.name)] = doc
            return doc
        def insert(**kwargs):
            doc.name = kwargs.get('set_name') or str(len(self.rows)+1)
            return save()
        doc.save, doc.insert = save, insert
        return doc


class TemplateInstallTests(unittest.TestCase):
    def setUp(self):
        self.site = FakeSite()
        spec = importlib.util.spec_from_file_location('template_install_test', ROOT / 'fieldpulse/scout_templates.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.site}): spec.loader.exec_module(self.module)
        self.module.install_templates()

    def test_install_is_idempotent_and_each_published_service_has_shared_and_final_questions(self):
        self.assertEqual(len(self.site.get_all('FP Questionnaire')), 15)
        self.assertEqual(len(self.site.get_all('FP Question')), 150)
        self.module.install_templates()
        self.assertEqual(len(self.site.get_all('FP Question')), 150)
        for row in self.site.get_all('FP Questionnaire'):
            self.assertEqual(row.status, 'Published')
            questions = self.site.get_all('FP Question', {'questionnaire': row.name})
            self.assertTrue({'S1','S2','S3','S4','S_EXTRA'} <= {q.question_code for q in questions})
            self.assertEqual(sum(json.loads(q.validation_json)['mandatory_evidence'] for q in questions), 1)

    def project(self):
        project = Record(doctype='Field Request', name='request', project_title='Plot check', field_brief='Check the blue gate on my plot.', request_type='Property Verification')
        self.module.prepare_project(project)
        return project

    def test_land_template_is_selected_and_remaining_checks_are_scopeable(self):
        project = self.project()
        self.assertEqual(project.scout_service, 'Land or plot check')
        self.assertEqual(project.scout_questionnaire, 'DD-land-v1')
        self.assertEqual(len(project.scout_checks), 5)
        self.assertEqual(project.scout_checks_confirmed, 0)
        evidence = next(q for q in self.site.get_all('FP Question', {'questionnaire': project.scout_questionnaire}) if q.question_code == '1.4')
        project.scout_checks = [Record(question=evidence.name)]
        self.module.prepare_project(project)
        self.assertEqual(len(project.scout_checks), 1)

    def test_required_evidence_question_cannot_be_removed(self):
        project = self.project()
        evidence = next(q for q in self.site.get_all('FP Question', {'questionnaire': project.scout_questionnaire}) if q.question_code == '1.4')
        project.scout_checks = [row for row in project.scout_checks if row.question != evidence.name]
        with self.assertRaisesRegex(ValueError, 'mandatory'): self.module.prepare_project(project)

    def test_source_drift_cannot_overwrite_a_published_template(self):
        doc = self.site.get_doc('FP Questionnaire', 'DD-land-v1')
        doc.schema_hash = 'changed'
        with self.assertRaisesRegex(ValueError, 'new version'): self.module.install_templates()

    def test_dispatch_pins_scope_and_refuses_unconfirmed_checks(self):
        project = self.project()
        self.site.rows[('Field Request', 'request')] = project
        task = Record(field_request='request', scout_profile='scout')
        with self.assertRaisesRegex(ValueError, 'confirm'): self.module.apply_to_task(task)
        evidence = next(q for q in self.site.get_all('FP Question', {'questionnaire': project.scout_questionnaire}) if q.question_code == '1.4')
        project.scout_checks = [Record(question=evidence.name)]
        project.scout_checks_confirmed = 1
        self.module.apply_to_task(task)
        self.assertEqual(task.questionnaire, 'DD-land-v1')
        self.assertEqual(set(json.loads(task.questionnaire_scope)), {'S1','S2','S3','S4','1.4','S_EXTRA'})
        self.assertEqual(json.loads(task.client_request_snapshot)['task_scope'], project.field_brief)

    def test_publishing_a_new_version_does_not_change_an_existing_projects_pin(self):
        project = self.project()
        newer = Record(doctype='FP Questionnaire', name='DD-land-v2', version=2, service_code='land', status='Published')
        self.site.rows[('FP Questionnaire', newer.name)] = newer
        self.module.prepare_project(project)
        self.assertEqual(project.scout_questionnaire, 'DD-land-v1')


if __name__ == '__main__': unittest.main()
