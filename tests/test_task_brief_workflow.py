import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def is_new(self): return self.get('new', True)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        from fieldpulse.task_briefs import brief_digest
        self.fixture = json.loads((ROOT/'tests/fixtures/task-brief-v1.json').read_text())
        self.frappe = MagicMock()
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.frappe.whitelist.return_value = lambda function: function
        self.frappe.PermissionError = PermissionError
        spec = importlib.util.spec_from_file_location('brief_workflow_test', ROOT/'fieldpulse/task_brief_workflow.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.frappe}):spec.loader.exec_module(self.module)
        self.project=Record(name='PROJECT',approved_task_brief='BRIEF',county='Kajiado',gps_accuracy_threshold_m=20)
        self.brief=Record(name='BRIEF',project='PROJECT',status='Approved',version=1,
            content_json=json.dumps(self.fixture['brief']),content_hash=brief_digest(self.fixture['brief']))
        self.site=Record(latitude=-1.3,longitude=36.8,geofence_radius_m=50)
        self.frappe.get_doc.side_effect=lambda doctype,name: {'Field Request':self.project,'DD Task Brief':self.brief,'FP Location':self.site}[doctype]
        self.task=Record(name='TASK',field_request='PROJECT',location='SITE',scout_profile='SCOUT',assigned_check_ids='["condition"]')

    def test_pin_is_independent_of_future_project_changes(self):
        self.module.pin_assignment(self.task)
        original=self.task.task_brief_snapshot
        self.brief.content_json='{}'
        self.module.pin_assignment(Record(self.task,new=False))
        self.assertEqual(original,self.task.task_brief_snapshot)
        self.assertEqual(json.loads(original)['site']['accuracy_threshold_m'],20)
        self.assertIsNone(self.task.questionnaire)

    def test_unapproved_and_foreign_briefs_cannot_dispatch(self):
        for change in ({'status':'Draft'},{'project':'OTHER'},{'content_hash':'tampered'}):
            with self.subTest(change=change):
                before=copy.deepcopy(self.brief);self.brief.update(change)
                with self.assertRaises(ValueError):self.module.pin_assignment(self.task)
                self.brief=before

    def test_assignment_requires_explicit_checks_and_destination(self):
        for change in ({'assigned_check_ids':'[]'},{'assigned_check_ids':'["unknown"]'},{'location':None}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                self.module.pin_assignment(Record(self.task,**change))

    def test_approved_assignments_are_immutable(self):
        self.module.pin_assignment(self.task)
        previous=Record(self.task,status='Assigned')
        for key in ('scout_profile','location','assigned_check_ids','task_brief_snapshot','task_brief_version'):
            current=Record(previous);current[key]='changed'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'immutable'):
                self.module.validate_task(current,previous)

    def test_completion_requires_coordinator_approval(self):
        self.module.pin_assignment(self.task)
        self.frappe.db.exists.return_value=False
        with self.assertRaisesRegex(ValueError,'coordinator'):
            self.module.validate_task(Record(self.task,status='Approved'),Record(self.task,status='Submitted'))

    def test_revision_evidence_cannot_cross_task_or_scout(self):
        original=Record(name='ORIGINAL',task='OTHER',agent='SCOUT')
        response=Record(name='REVISION',task='TASK',agent='SCOUT',rework_of='ORIGINAL')
        self.frappe.get_doc.side_effect=lambda *args:original
        with self.assertRaisesRegex(ValueError,'lineage'):self.module.evidence_rows(response)
        self.frappe.get_all.assert_not_called()
        original.task='TASK';original.agent='OTHER'
        with self.assertRaisesRegex(ValueError,'lineage'):self.module.evidence_rows(response)
        original.agent='SCOUT'
        self.frappe.get_all.return_value=[]
        self.assertEqual(self.module.evidence_rows(response),[])
        self.assertEqual(self.frappe.get_all.call_args.kwargs['filters']['task_response'],['in',['REVISION','ORIGINAL']])

    def test_cancelled_or_old_version_allocations_cannot_omit_required_checks(self):
        for rows,want in [([],False),([Record(task_brief_version='OLD',assigned_check_ids='["condition"]')],False),
            ([Record(task_brief_version='BRIEF',assigned_check_ids='["condition"]')],True)]:
            self.frappe.get_all.return_value=rows
            self.assertEqual(self.module.coverage_ready(['PROJECT']),want)

    def test_terminal_retry_is_read_only_and_checks_uuid_ownership(self):
        self.module.pin_assignment(self.task)
        self.task.status='Approved'
        response=Record(name='RESPONSE',task='TASK',agent='SCOUT',status='Submitted')
        response.save=MagicMock()
        self.frappe.db.exists.return_value='RESPONSE'
        self.frappe.get_doc.side_effect=lambda kind,name:self.task if kind=='Field Task' else response
        payload=dict(client_uuid='uuid',task='TASK',brief_hash=self.brief.content_hash,reconcile_only=True)
        api=type('Api',(),{'_get_scout_profile_for_user':lambda:Record(name='SCOUT')})
        with patch.dict(sys.modules,{'fieldpulse.api':api}):
            self.assertEqual(self.module.save_response(payload)['task_status'],'Approved')
            response.save.assert_not_called()
            response.agent='OTHER'
            with self.assertRaisesRegex(ValueError,'another assignment'):self.module.save_response(payload)

    def test_closed_unsubmitted_retry_does_not_write(self):
        self.module.pin_assignment(self.task);self.task.status='Cancelled'
        self.frappe.db.exists.return_value=None
        self.frappe.get_doc.side_effect=lambda *args:self.task
        api=type('Api',(),{'_get_scout_profile_for_user':lambda:Record(name='SCOUT')})
        with patch.dict(sys.modules,{'fieldpulse.api':api}):
            result=self.module.save_response(dict(client_uuid='uuid',task='TASK',brief_hash=self.brief.content_hash,reconcile_only=True))
        self.assertEqual(result['status'],'Missing')
        self.assertEqual(result['task_status'],'Cancelled')
        self.frappe.new_doc.return_value.save.assert_not_called()

    def test_clarification_creates_revision_and_delivers_instructions(self):
        self.module.pin_assignment(self.task)
        self.task.status='Submitted';self.task.check_permission=MagicMock()
        def save_task(**kwargs):self.task.status='In Progress'
        self.task.save=save_task
        response=Record(name='RESPONSE',task='TASK',agent='SCOUT',status='Submitted',qa_status='Pending',
            arrival_check_json='{}',brief_answers_json='{}',final_review_json='{}')
        revision=MagicMock(name='revision');revision.name='REVISION'
        self.frappe.get_doc.side_effect=lambda kind,name=None:revision if isinstance(kind,dict) else self.task if kind=='Field Task' else response
        self.frappe.db.get_value.return_value='TASK'
        notifications=MagicMock()
        with patch.dict(sys.modules,{'fieldpulse.scout_submissions':type('Review',(),{'require_reviewer':lambda:None}),
                'fieldpulse.scout_notifications':notifications}),patch.object(self.module,'evidence_records',return_value=[]),patch.object(self.module,'evaluate_submission',return_value={'complete':True,'status':'pending_coordinator_review'}):
            result=self.module.review_response('RESPONSE','Request clarification','Clarify which boundary was visible')
        self.assertEqual(result['status'],'In Progress')
        revision.insert.assert_called_once()
        notifications.queue_rework.assert_called_once()
        self.assertEqual(notifications.queue_rework.call_args.args[-1],'Clarify which boundary was visible')
        payload=self.frappe.get_doc.call_args.args[0]
        self.assertEqual(payload['rework_of'],'RESPONSE')
        self.assertFalse(json.loads(payload['final_review_json'])['declaration'])


if __name__=='__main__':unittest.main()
