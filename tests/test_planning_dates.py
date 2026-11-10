import importlib.util
from datetime import date
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class PlanningDatesTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.throw.side_effect = ValueError
        utils = types.ModuleType('frappe.utils')
        utils.getdate = lambda value=None: date.fromisoformat(str(value)) if value else date(2026, 11, 10)
        spec = importlib.util.spec_from_file_location('planning_dates_test', Path(__file__).parents[1] / 'fieldpulse/planning_dates.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.frappe, 'frappe.utils': utils}):
            spec.loader.exec_module(self.module)

    def test_new_changed_and_historical_dates(self):
        for doctype, fields in self.module.FIELDS.items():
            for field in fields:
                for value, previous, rejected in [
                    ('2026-11-09', None, True),
                    ('2026-11-10', None, False),
                    ('2026-11-11', None, False),
                    ('2026-11-09', '2026-11-09', False),
                    ('2026-11-08', '2026-11-09', True),
                    (None, None, False),
                ]:
                    with self.subTest(doctype=doctype, value=value, previous=previous):
                        doc = MagicMock(doctype=doctype)
                        doc.get.return_value = value
                        old = MagicMock() if previous else None
                        if old: old.get.return_value = previous
                        doc.get_doc_before_save.return_value = old
                        if rejected:
                            with self.assertRaises(ValueError): self.module.validate(doc)
                        else:
                            self.module.validate(doc)
