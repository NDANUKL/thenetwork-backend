import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class ProjectLocationVerificationTests(unittest.TestCase):
    def setUp(self):
        def throw(message):
            raise ValueError(message)
        api = SimpleNamespace(throw=throw, session=SimpleNamespace(user='coordinator'),
                              utils=SimpleNamespace(now_datetime=lambda: '2026-10-25 12:00:00'))
        spec = importlib.util.spec_from_file_location('location_verification_test', ROOT / 'fieldpulse/project_locations.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'frappe': api}):
            spec.loader.exec_module(self.module)

    def test_project_form_exposes_editable_verification_table(self):
        schema = json.loads((ROOT / 'fieldpulse/fieldpulse/doctype/field_request/field_request.json').read_text())
        self.assertIn('project_locations', schema['field_order'])
        table = next(f for f in schema['fields'] if f['fieldname'] == 'project_locations')
        self.assertEqual(table['options'], 'DD Request Site')
        self.assertFalse(table.get('read_only'))
        child = json.loads((ROOT / 'fieldpulse/fieldpulse/doctype/dd_request_site/dd_request_site.json').read_text())
        checkbox = next(f for f in child['fields'] if f['fieldname'] == 'location_verified')
        self.assertFalse(checkbox.get('read_only'))

    def test_verifying_precise_destination_records_confirmation(self):
        site = Row(name='site', county='Nairobi', latitude=-1.2, longitude=36.8,
                   pin_type='Entrance', location_verified=1)
        project = Row(diaspora_request='request', county='Nairobi', project_locations=[site],
                      is_new=lambda: True)
        self.module.validate_locations(project)
        self.assertEqual(site.confirmation_status, 'Confirmed for dispatch')
        self.assertEqual(site.confirmed_by, 'coordinator')
        self.assertEqual(len(json.loads(project.dd_site_locations)), 1)
        site.pin_type = 'Approximate area'
        with self.assertRaisesRegex(ValueError, 'precise entrance'):
            self.module.validate_locations(project)

    def test_assignment_still_requires_every_location_verified(self):
        task = Row(is_new=lambda: True)
        project = Row(requires_verified_location=1, project_locations=[Row(confirmation_status='Needs confirmation')])
        with self.assertRaisesRegex(ValueError, 'Project locations table'):
            self.module.map_task_navigation(task, project)
