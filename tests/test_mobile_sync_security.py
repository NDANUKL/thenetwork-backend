import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

class MobileSyncSecurity(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        import json
        self.f.parse_json.side_effect = json.loads
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

    def test_approved_history_is_in_full_and_delta_sync_without_questionnaires(self):
        from datetime import datetime
        class Row(dict):
            __getattr__ = dict.get
        historical = Row(name='old-approved', task_number='TK-2026-00010',
                         status='Approved', scout_profile='scout', task_brief_version=None)
        cutover = types.SimpleNamespace(open_legacy_tasks=lambda scout: [], cancelled_legacy_tasks=lambda *args: [])
        inbox = types.SimpleNamespace(notification_payload=lambda: [])
        self.api.now_datetime.return_value = datetime(2026, 10, 30, 12)
        self.api.site_datetime_iso = lambda value: value
        with patch.dict(sys.modules, {'fieldpulse.task_brief_cutover': cutover, 'fieldpulse.scout_inbox': inbox}):
            for since in (None, '2026-10-29 12:00:00'):
                self.f.get_all.reset_mock()
                self.f.get_all.side_effect = [[], [historical]]
                result = self.api.sync_pull_assignments(since=since, task_brief_version=1)
                filters = self.f.get_all.call_args_list[1].kwargs['filters']
                self.assertEqual(filters['scout_profile'], 'scout')
                self.assertEqual(filters['status'], 'Approved')
                self.assertEqual(filters['task_brief_version'], ['is', 'not set'])
                self.assertEqual(filters.get('modified'), ['>', since] if since else None)
                self.assertEqual(result['tasks'][0]['status'], 'Approved')
                self.assertIsNone(result['tasks'][0]['task_brief_version'])
                self.assertEqual(result['assigned_task_ids'], ['old-approved'] if not since else None)
                self.assertEqual(result['questionnaires'], [])
                self.assertEqual(result['questions'], [])

    def test_open_legacy_guard_still_blocks_history_sync(self):
        cutover = types.SimpleNamespace(open_legacy_tasks=lambda scout: ['unresolved'], cancelled_legacy_tasks=lambda *args: [])
        with patch.dict(sys.modules, {'fieldpulse.task_brief_cutover': cutover}):
            with self.assertRaisesRegex(PermissionError, 'cutover is pending'):
                self.api.sync_pull_assignments(task_brief_version=1)
        self.f.get_all.assert_not_called()

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
        with patch.dict(sys.modules, {'frappe.utils':utils,'fieldpulse.task_brief_workflow':rework,'fieldpulse.task_brief_cutover':types.SimpleNamespace(open_legacy_tasks=lambda scout:[],cancelled_legacy_tasks=lambda *args:[]),'fieldpulse.scout_inbox':types.SimpleNamespace(notification_payload=lambda:[])}):
            result = self.api.sync_pull_assignments(protocol_version=2,visit_workflow_version=2,rework_version=2,questionnaire_editor_version=1,task_brief_version=1)
        self.assertEqual(result['tasks'][0]['due_at'],'2026-10-27T17:00:00+03:00')
        self.assertEqual(result['tasks'][0]['assigned_at'],'2026-10-26T09:00:00+03:00')
        self.assertEqual(result['tasks'][0]['server_updated_at'],'2026-10-26T10:00:00+03:00')
        self.assertEqual(result['server_time'],'2026-10-26T12:00:00')
