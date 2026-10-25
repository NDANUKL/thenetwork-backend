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
        with self.assertRaisesRegex(ValueError, 'Location verified'):
            self.module.map_task_navigation(task, project)


    def test_arrangements_follow_each_project_location_and_refresh_when_changed(self):
        first = Row(site_label='Land entrance', contact_name='Jane', contact_phone='0712345678', access_notes='Meet at gate')
        second = Row(site_label='Store', contact_name='Ali', access_notes='Call before arrival')
        project = Row(diaspora_request='request', project_locations=[first, second])
        self.module.sync_contact_access(project)
        self.assertEqual(project.scout_contact_access, 'Land entrance\nContact: Jane - 0712345678\nAccess: Meet at gate\n\nStore\nContact: Ali\nAccess: Call before arrival')
        first.contact_phone = '0798765432'
        project.project_locations = [first]
        self.module.sync_contact_access(project)
        self.assertIn('0798765432', project.scout_contact_access)
        self.assertNotIn('Ali', project.scout_contact_access)
        self.assertNotIn('0712345678', project.scout_contact_access)
        project.project_locations = []
        self.module.sync_contact_access(project)
        self.assertEqual(project.scout_contact_access, '')

    def test_blank_locations_do_not_invent_arrangements_and_manual_projects_stay_editable(self):
        self.assertEqual(self.module.contact_access_summary([Row(site_label='No contact supplied')]), '')
        manual = Row(scout_contact_access='Agreed by telephone')
        self.module.sync_contact_access(manual)
        self.assertEqual(manual.scout_contact_access, 'Agreed by telephone')

    def test_only_matching_customer_sites_supply_project_contacts(self):
        source = Row(project_contract_version=1, customer_sites=[
            Row(name='a', project_ids='["maize"]', site_label='Maize plot', contact_name='Jane'),
            Row(name='b', project_ids='["shop"]', site_label='Shop', contact_name='Ali')])
        target = Row(project_locations=[])
        def append(field, values):
            row = Row(values)
            target[field].append(row)
            return row
        target.append = append
        self.module.sync_locations(target, source, {'id': 'maize'})
        summary = self.module.contact_access_summary(target.project_locations)
        self.assertIn('Jane', summary)
        self.assertNotIn('Ali', summary)

    def test_derived_summary_is_read_only_and_manual_next_action_hidden(self):
        schema = json.loads((ROOT / 'fieldpulse/fieldpulse/doctype/field_request/field_request.json').read_text())
        field = next(f for f in schema['fields'] if f['fieldname'] == 'scout_contact_access')
        self.assertEqual(field['read_only_depends_on'], 'eval:!!doc.diaspora_request')
        schema = json.loads((ROOT / 'fieldpulse/fieldpulse/doctype/diaspora_request/diaspora_request.json').read_text())
        field = next(f for f in schema['fields'] if f['fieldname'] == 'customer_next_action')
        self.assertEqual(field['hidden'], 1)
        self.assertEqual(field['read_only'], 1)


    def test_source_checkbox_confirmation_and_revocation_carry_to_project(self):
        site = Row(name='source', project_ids='["maize"]', site_label='Plot', county='Nairobi', location_verified=1)
        source = Row(project_contract_version=1, customer_sites=[site])
        target = Row(project_locations=[])
        def append(field, values):
            row = Row(values); target[field].append(row); return row
        target.append = append
        self.module.sync_locations(target, source, {'id': 'maize'})
        row = target.project_locations[0]
        self.assertEqual(row.location_verified, 1)
        self.assertEqual(row.confirmation_status, 'Confirmed for dispatch')
        site.location_verified = 0
        self.module.sync_locations(target, source, {'id': 'maize'})
        self.assertEqual(row.location_verified, 0)
        self.assertEqual(row.confirmation_status, 'Needs confirmation')
        # Project-side verification is retained when the source hasn't changed.
        row.location_verified = 1
        row.confirmation_status = 'Confirmed for dispatch'
        self.module.sync_locations(target, source, {'id': 'maize'})
        self.assertEqual(row.location_verified, 1)

    def test_source_checkbox_cannot_confirm_a_different_project_destination(self):
        values = {field: None for field in self.module.LOCATION_FIELDS}
        values.update(site_label='Plot', county='Nairobi', latitude=-1.2, longitude=36.8)
        site = Row(values, name='source', project_ids='["maize"]', location_verified=1)
        original_snapshot = json.dumps(values)
        row = Row(values, source_site_id='source', source_location_snapshot=original_snapshot, location_verified=0)
        row.latitude = -1.3
        source = Row(project_contract_version=1, customer_sites=[site])
        target = Row(project_locations=[row])
        self.module.sync_locations(target, source, {'id': 'maize'})
        self.assertEqual(row.latitude, -1.3)
        self.assertEqual(row.location_verified, 0)
