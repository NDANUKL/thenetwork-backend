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

    def test_mobile_response_dates_normalized_before_save(self):
        from datetime import datetime
        self.f.get_doc.return_value = types.SimpleNamespace(name='task', scout_profile='scout', location='location', status='Assigned')
        self.f.db.exists.return_value = None
        self.api._apply_geofence_check = MagicMock()
        utils = types.ModuleType('frappe.utils')
        utils.get_system_timezone = lambda: 'Africa/Nairobi'
        with patch.dict(sys.modules, {'frappe.utils': utils}):
            self.api._upsert_task_response(dict(client_uuid='new', task='task', location='location', status='Draft', started_at='2026-10-23T15:09:17.641Z', submitted_at=None, client_updated_at='2026-10-23T15:10:00Z'))
        doc = self.f.new_doc.return_value
        doc.set.assert_any_call('started_at', datetime(2026, 10, 23, 18, 9, 17, 641000))
        doc.set.assert_any_call('submitted_at', None)
        doc.set.assert_any_call('client_updated_at', datetime(2026, 10, 23, 18, 10))
        doc.save.assert_called_once()

    def test_mobile_contract_advertises_recovery_and_authoritative_membership(self):
        result = self.api._mobile_capabilities()
        self.assertEqual(result['contract'], 1)
        self.assertTrue(result['authoritative_assignments'])
        self.assertTrue(result['resumable_submission'])
        self.assertEqual(result['visit_workflow_version'], 2)

    def test_retry_after_lost_submission_ack_returns_terminal_state(self):
        task = types.SimpleNamespace(name='task', scout_profile='scout', location='location', status='Submitted')
        response = types.SimpleNamespace(name='response', task='task', agent='scout', status='Submitted')
        self.f.get_doc.side_effect = [task, response]
        result = self.api._upsert_task_response({'client_uuid':'known', 'task':'task', 'location':'location', 'status':'Draft'})
        self.assertEqual(result['response_status'], 'Submitted')
        self.assertEqual(result['server_id'], 'response')
        self.f.new_doc.assert_not_called()

    def test_assignment_times_include_site_offset_but_cursor_stays_site_local(self):
        from datetime import datetime
        class Row(dict):
            __getattr__ = dict.get
        task = Row(name='task',status='Assigned',modified=datetime(2026,10,26,10),creation=datetime(2026,10,25,8),due_at=datetime(2026,10,27,17),assigned_at=datetime(2026,10,26,9))
        self.f.get_all.return_value = [task]
        self.api.now_datetime.return_value = datetime(2026,10,26,12)
        utils = types.ModuleType('frappe.utils')
        utils.get_system_timezone = lambda: 'Africa/Nairobi'
        rework = types.ModuleType('fieldpulse.scout_rework')
        rework.revision_payload = lambda task: None
        with patch.dict(sys.modules, {'frappe.utils':utils,'fieldpulse.scout_rework':rework,'fieldpulse.scout_inbox':types.SimpleNamespace(notification_payload=lambda:[])}):
            result = self.api.sync_pull_assignments(protocol_version=2,visit_workflow_version=2,rework_version=2,questionnaire_editor_version=1)
        self.assertEqual(result['tasks'][0]['due_at'],'2026-10-27T17:00:00+03:00')
        self.assertEqual(result['tasks'][0]['assigned_at'],'2026-10-26T09:00:00+03:00')
        self.assertEqual(result['tasks'][0]['server_updated_at'],'2026-10-26T10:00:00+03:00')
        self.assertEqual(result['server_time'],'2026-10-26T12:00:00')
