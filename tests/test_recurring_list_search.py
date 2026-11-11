import ast
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).parents[1]

class RecurringListSearchTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.utils.cint.side_effect = lambda value: int(value or 0)
        nodes = ast.parse((ROOT / 'fieldpulse/recurring.py').read_text(encoding='utf-8'))
        node = next(n for n in nodes.body if isinstance(n, ast.FunctionDef) and n.name == 'list_plans')
        env = dict(frappe=self.f, api=lambda fn: fn, account=lambda: 'OWN', PLAN='DD Recurring Plan', OCCURRENCE='DD Recurring Occurrence', today=lambda: date(2026, 11, 11), timedelta=timedelta, LEAD_DAYS=14, summary=lambda doc: doc)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'recurring.py', 'exec'), env)
        self.call = env['list_plans']
        self.f.get_doc.side_effect = lambda doctype, name: {'name': name}

    def test_search_applies_before_five_item_pagination_and_count(self):
        self.f.get_all.side_effect = [[SimpleNamespace(total=12)], [SimpleNamespace(name=str(i)) for i in range(6)], []]
        result = self.call(page=2, search='warehouse', page_size=5)
        self.assertEqual(len(result['plans']), 5)
        self.assertTrue(result['has_more'])
        self.assertEqual(result['total'], 12)
        count, rows, upcoming = self.f.get_all.call_args_list
        self.assertEqual(rows.kwargs['limit_start'], 5)
        self.assertEqual(rows.kwargs['limit_page_length'], 6)
        self.assertEqual(count.kwargs['or_filters'], rows.kwargs['or_filters'])
        self.assertIn(['title', 'like', '%warehouse%'], rows.kwargs['or_filters'])
        for call in (count, rows, upcoming):
            self.assertEqual(call.kwargs['filters']['customer_account'], 'OWN')

    def test_status_filter_applies_to_both_matching_count_and_page(self):
        for status in ('Active', 'Pending review', 'Paused'):
            self.f.get_all.reset_mock()
            self.f.get_all.side_effect = [[SimpleNamespace(total=0)], [], []]
            self.call(status=status, search='warehouse', page_size=5)
            for call in self.f.get_all.call_args_list[:2]:
                self.assertEqual(call.kwargs['filters'], {'customer_account': 'OWN', 'status': status})
                self.assertIn(['title', 'like', '%warehouse%'], call.kwargs['or_filters'])

    def test_default_page_size_is_preserved_and_empty_results_work(self):
        self.f.get_all.side_effect = [[SimpleNamespace(total=0)], [], []]
        result = self.call()
        self.assertEqual(result['plans'], [])
        self.assertFalse(result['has_more'])
        self.assertEqual(self.f.get_all.call_args_list[1].kwargs['limit_page_length'], 21)
        self.assertEqual(self.f.get_all.call_args_list[1].kwargs['or_filters'], [])

    def test_page_size_and_search_are_bounded(self):
        self.f.get_all.side_effect = [[SimpleNamespace(total=0)], [], []]
        self.call(page=-1, search='x'*500, page_size=500)
        rows = self.f.get_all.call_args_list[1].kwargs
        self.assertEqual(rows['limit_start'], 0)
        self.assertEqual(rows['limit_page_length'], 21)
        self.assertEqual(len(rows['or_filters'][0][2]), 102)

if __name__ == '__main__':
    unittest.main()
