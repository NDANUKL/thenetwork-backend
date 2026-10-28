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
        utils.get_system_timezone = lambda: "Africa/Nairobi"
        helpers = types.ModuleType('fieldpulse.utils')
        helpers.haversine_distance_m = MagicMock()
        spec = importlib.util.spec_from_file_location('sync_api_test', Path(__file__).parents[1] / 'fieldpulse/api.py')
        self.api = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': utils, 'fieldpulse.utils': helpers}): spec.loader.exec_module(self.api)
        self.api._get_scout_profile_for_user = lambda: types.SimpleNamespace(name='scout')
    def test_questionnaire_mutation_api_is_not_exposed(self):
        for name in ('sync_push_responses','_upsert_task_response','_upsert_question_response'):
            self.assertFalse(hasattr(self.api,name))

    def test_mobile_contract_advertises_recovery_and_authoritative_membership(self):
        result = self.api._mobile_capabilities()
        self.assertEqual(result['contract'], 1)
        self.assertTrue(result['authoritative_assignments'])
        self.assertTrue(result['resumable_submission'])
        self.assertEqual(result['visit_workflow_version'], 2)

    def test_assignment_times_include_site_offset_but_cursor_stays_site_local(self):
        from datetime import datetime
        class Row(dict):
            __getattr__ = dict.get
        task = Row(task_brief_version='BRIEF',name='task',status='Assigned',modified=datetime(2026,10,26,10),creation=datetime(2026,10,25,8),due_at=datetime(2026,10,27,17),assigned_at=datetime(2026,10,26,9))
        self.f.get_all.return_value = [task]
        self.api.now_datetime.return_value = datetime(2026,10,26,12)
        utils = types.ModuleType('frappe.utils')
        utils.get_system_timezone = lambda: 'Africa/Nairobi'
        rework = types.ModuleType('fieldpulse.scout_rework')
        rework.revision_payload = lambda task: None
        with patch.dict(sys.modules, {'frappe.utils':utils,'fieldpulse.task_brief_workflow':rework,'fieldpulse.task_brief_cutover':types.SimpleNamespace(open_legacy_tasks=lambda scout:[]),'fieldpulse.scout_inbox':types.SimpleNamespace(notification_payload=lambda:[])}):
            result = self.api.sync_pull_assignments(protocol_version=2,visit_workflow_version=2,rework_version=2,questionnaire_editor_version=1,task_brief_version=1)
        self.assertEqual(result['tasks'][0]['due_at'],'2026-10-27T17:00:00+03:00')
        self.assertEqual(result['tasks'][0]['assigned_at'],'2026-10-26T09:00:00+03:00')
        self.assertEqual(result['tasks'][0]['server_updated_at'],'2026-10-26T10:00:00+03:00')
        self.assertEqual(result['server_time'],'2026-10-26T12:00:00')
