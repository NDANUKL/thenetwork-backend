import unittest
import types
from datetime import date
from unittest.mock import Mock, patch
from tests.test_native_integration import load


class TaskNumberTests(unittest.TestCase):
    def test_number_series_uses_creation_year(self):
        naming = Mock(return_value='TK-2026-00001')
        module = load('task_numbers_test', 'fieldpulse/task_numbers.py', {
            'frappe.model.naming': types.SimpleNamespace(make_autoname=naming),
            'frappe.utils': types.SimpleNamespace(getdate=lambda value: date.fromisoformat(value[:10]) if value else date(2026, 10, 23)),
        })
        self.assertEqual(module.next_task_number(), 'TK-2026-00001')
        naming.assert_called_with('TK-2026-.#####')
        module.next_task_number('2025-12-31 12:00:00')
        naming.assert_called_with('TK-2025-.#####')
