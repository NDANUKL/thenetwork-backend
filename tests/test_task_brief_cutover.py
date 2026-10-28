import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock()
        self.f.throw.side_effect=lambda msg:(_ for _ in ()).throw(ValueError(msg))
        spec=importlib.util.spec_from_file_location('cutover_tests',Path(__file__).parents[1]/'fieldpulse/task_brief_cutover.py')
        self.m=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.m)

    def test_open_legacy_work_blocks_rollout_without_mutation(self):
        self.f.get_all.return_value=[type('Task',(),{'name':'OPEN'})()]
        with self.assertRaisesRegex(ValueError,'cutover blocked'):self.m.assert_ready()
        self.f.db.set_value.assert_not_called()
        self.assertFalse(self.m.inventory()['device_work_verified'])

    def test_finished_cutover_and_fresh_install_can_migrate(self):
        self.f.get_all.return_value=[]
        self.m.assert_ready()
        self.assertTrue(self.m.inventory()['ready'])
        self.f.db.exists.return_value=False
        self.f.get_all.reset_mock();self.m.assert_ready();self.f.get_all.assert_not_called()

    def test_inventory_scopes_scout_and_excludes_terminal_tasks(self):
        self.m.open_legacy_tasks('SCOUT')
        filters=self.f.get_all.call_args.kwargs['filters']
        self.assertEqual(filters['scout_profile'],'SCOUT')
        self.assertEqual(filters['task_brief_version'],['is','not set'])
        self.assertEqual(filters['status'],['not in',['Approved','Cancelled']])
