import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

class MobileSyncSecurity(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.PermissionError = PermissionError
        def reject(message, *args): raise PermissionError(message)
        self.f.throw.side_effect = reject
        utils = types.ModuleType('frappe.utils')
        utils.now_datetime = MagicMock()
        helpers = types.ModuleType('fieldpulse.utils')
        helpers.haversine_distance_m = MagicMock()
        spec = importlib.util.spec_from_file_location('sync_api_test', Path(__file__).parents[1] / 'fieldpulse/api.py')
        self.api = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': utils, 'fieldpulse.utils': helpers}): spec.loader.exec_module(self.api)
        self.api._get_scout_profile_for_user = lambda: types.SimpleNamespace(name='scout')
    def test_other_scout_answer_fails_before_uuid_lookup(self):
        self.f.get_doc.side_effect = [types.SimpleNamespace(task='task', agent='other'), types.SimpleNamespace(scout_profile='other')]
        with self.assertRaises(PermissionError): self.api._upsert_question_response({'client_uuid': 'known', 'task_response': 'response'})
        self.f.db.exists.assert_not_called()
    def test_task_uuid_cannot_be_rebound(self):
        self.f.get_doc.side_effect = [types.SimpleNamespace(name='task', scout_profile='scout', location='location', status='Assigned'), types.SimpleNamespace(task='other', agent='scout')]
        with self.assertRaises(PermissionError): self.api._upsert_task_response({'client_uuid': 'known', 'task': 'task', 'location': 'location', 'status': 'Draft'})
    def test_failed_item_rolled_back(self):
        self.api._upsert_task_response = MagicMock(side_effect=ValueError('failed'))
        result = self.api.sync_push_responses([{'client_uuid': 'id'}], [])
        self.assertEqual(result['accepted'], [])
        self.f.db.rollback.assert_called_once_with(save_point='sync_item')
        self.f.db.commit.assert_called_once()
