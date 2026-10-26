"""Prevent duplicate native DocFields from inserting the same child row twice."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


class SchemaIntegrityTests(unittest.TestCase):
    def test_native_fields_and_field_order_are_unique(self):
        for path in (ROOT / 'fieldpulse/fieldpulse/doctype').glob('*/*.json'):
            schema = json.loads(path.read_text(encoding='utf-8'))
            if schema.get('doctype') != 'DocType':
                continue
            with self.subTest(doctype=schema['name']):
                fields = [field['fieldname'] for field in schema.get('fields', [])]
                self.assertEqual(len(fields), len(set(fields)), path)
                order = schema.get('field_order', [])
                self.assertEqual(len(order), len(set(order)), path)

    def load_patch(self, fields):
        frappe = MagicMock()
        frappe.get_meta.return_value.fields = [types.SimpleNamespace(**field) for field in fields]
        frappe.throw.side_effect = ValueError
        path = ROOT / 'fieldpulse/patches/v1_0/deduplicate_project_locations.py'
        spec = importlib.util.spec_from_file_location('location_metadata_patch', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': frappe}):
            spec.loader.exec_module(module)
        return module, frappe

    def test_repair_reloads_schema_without_touching_customer_rows(self):
        module, frappe = self.load_patch([dict(fieldname='project_locations', fieldtype='Table', options='DD Request Site')])
        module.execute()
        frappe.reload_doc.assert_called_once_with('fieldpulse', 'doctype', 'field_request', force=True)
        frappe.clear_cache.assert_called_once_with(doctype='Field Request')
        frappe.db.delete.assert_not_called()
        frappe.db.sql.assert_not_called()

    def test_repair_fails_if_duplicate_metadata_remains(self):
        field = dict(fieldname='project_locations', fieldtype='Table', options='DD Request Site')
        module, frappe = self.load_patch([field, field])
        with self.assertRaises(ValueError):
            module.execute()
        frappe.clear_cache.assert_not_called()
