import importlib.util
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value


class BriefJobTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.whitelist.return_value = lambda fn: fn
        self.frappe.session.user = 'service@example.test'
        self.frappe.get_roles.return_value = ['System Manager']
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.now = datetime(2026, 11, 15, 12)
        self.frappe.utils.now_datetime.return_value = self.now
        self.frappe.utils.get_datetime.side_effect = datetime.fromisoformat
        self.patch = patch.dict(sys.modules, {'frappe': self.frappe})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        path = Path(__file__).parents[1] / 'fieldpulse/task_brief_jobs.py'
        spec = importlib.util.spec_from_file_location('test_brief_jobs_module', path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.source = Record(name='REQ', submitted_assessment='{}',
            project_details=json.dumps([{'id': 'project-1', 'eligibility': 'supported', 'service_category': 'construction_progress'}]),
            task_brief_jobs=json.dumps({'project-1': {'status': 'Pending', 'attempts': 0}}))
        self.frappe.get_doc.return_value = self.source

    def test_only_new_submissions_create_pending_jobs_for_supported_projects(self):
        self.module.initialise(self.source)
        self.assertNotIn('task_brief_generation_status', self.source)
        self.source.submitted_assessment = json.dumps({'brief_generation_mode': 'after_submission_v1'})
        self.source.project_details = json.dumps([{'id': 'a', 'eligibility': 'supported'}, {'id': 'b', 'eligibility': 'unsupported'}])
        self.module.initialise(self.source)
        self.assertEqual(json.loads(self.source.task_brief_jobs), {'a': {'status': 'Pending', 'attempts': 0}})
        self.assertEqual(self.source.task_brief_generation_status, 'Preparing')

    def test_concurrent_claims_wait_until_lease_expires(self):
        self.source.task_brief_jobs = json.dumps({'project-1': {'status': 'Processing', 'attempts': 1, 'lease_until': str(self.now + timedelta(minutes=1))}})
        self.assertEqual(self.module.claim('REQ', 'project-1'), {'busy': True})
        self.frappe.db.set_value.assert_not_called()

    def test_expired_claim_is_recovered_with_new_token(self):
        self.source.task_brief_jobs = json.dumps({'project-1': {'status': 'Processing', 'attempts': 1, 'token': 'old', 'lease_until': str(self.now - timedelta(seconds=1))}})
        result = self.module.claim('REQ', 'project-1')
        self.assertNotEqual(result['token'], 'old')
        written = self.frappe.db.set_value.call_args.args[2]
        self.assertEqual(json.loads(written['task_brief_jobs'])['project-1']['attempts'], 2)

    def test_exhausted_claim_becomes_visible_failure(self):
        self.source.task_brief_jobs = json.dumps({'project-1': {'status': 'Pending', 'attempts': 3}})
        self.assertEqual(self.module.claim('REQ', 'project-1'), {'skip': True})
        self.assertEqual(self.frappe.db.set_value.call_args.args[2]['task_brief_generation_status'], 'Needs attention')

    def test_stale_completion_cannot_replace_result(self):
        self.assertEqual(self.module.complete('REQ', 'project-1', 'old', brief={}), {'stale': True})
        self.frappe.db.set_value.assert_not_called()

    def test_failed_attempt_returns_to_pending_until_budget_exhausted(self):
        self.source.task_brief_jobs = json.dumps({'project-1': {'status': 'Processing', 'attempts': 1, 'token': 'current'}})
        self.module.complete('REQ', 'project-1', 'current', error='provider error')
        saved = self.frappe.db.set_value.call_args.args[2]
        self.assertEqual(json.loads(saved['task_brief_jobs'])['project-1']['status'], 'Pending')
        self.assertEqual(saved['task_brief_generation_status'], 'Preparing')

    def test_customer_cannot_claim_generation_jobs(self):
        self.frappe.get_roles.return_value = ['DD Customer']
        with self.assertRaisesRegex(ValueError, 'trusted generation service'):
            self.module.claim('REQ', 'project-1')

    def test_completed_brief_is_saved_once_without_rewriting_submission(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/task-brief-v1.json').read_text())['brief']
        self.source.project_details = json.dumps([{'id': 'project-1', 'eligibility': 'supported', 'service_category': fixture['category']}])
        self.source.task_brief_jobs = json.dumps({'project-1': {'status': 'Processing', 'attempts': 1, 'token': 'current'}})
        self.frappe.get_all.return_value = []
        self.module.complete('REQ', 'project-1', 'current', brief=fixture)
        writes = self.frappe.db.set_value.call_args_list
        self.assertEqual(writes[0].args[2], 'project_details')
        self.assertEqual(json.loads(writes[0].args[3])[0]['task_brief']['title'], fixture['title'])
        self.assertEqual(writes[1].args[2]['task_brief_generation_status'], 'Ready')
        self.assertNotIn('submitted_assessment', writes[1].args[2])
        self.assertNotIn('submission_snapshot', writes[1].args[2])
        self.source.task_brief_jobs = writes[1].args[2]['task_brief_jobs']
        self.frappe.db.set_value.reset_mock()
        self.assertEqual(self.module.complete('REQ', 'project-1', 'current', brief=fixture), {'stale': True})
        self.frappe.db.set_value.assert_not_called()


if __name__ == '__main__': unittest.main()
