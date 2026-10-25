import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from fieldpulse.scout_lineage import evidence_origin_allowed

ROOT = Path(__file__).parents[1]


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def set(self, key, value): self[key] = value


def load(name, path, frappe):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe': frappe, 'requests': MagicMock()}): spec.loader.exec_module(module)
    return module


class ReworkTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.f.utils.now_datetime.return_value = '2026-10-24 12:00:00'
        self.module = load('rework_tests', 'fieldpulse/scout_rework.py', self.f)
        self.task = Record(name='task', scout_profile='scout', status='In Progress', rework_response='revision', client_request_snapshot='{"protocol_version":2}')
        self.source = Record(name='source', task='task', agent='scout', location='site', status='Submitted', qa_status='Failed',
            arrival_check_json='{"status":"Inside"}', final_review_json='{"coverage":"Yes"}', started_at='2026-10-24 09:00:00')
        self.original = Record(question='q1', question_code='1.1', question_type='service_check',
            answer_json='{"result":"Yes","text":"North wall"}', answer_text='North wall',
            evidence_links=[Record(evidence='photo', requirement_id='1.1::overview', support_note='Wall overview')])
        self.created = []
        def doc(values, name=None):
            if isinstance(values, str): return self.original
            record = Record(values, name='revision' if values['doctype'] == 'FP Task Response' else 'new-answer', flags=Record())
            record.insert = lambda **kw: self.created.append(record) or record
            return record
        self.f.get_doc.side_effect = doc
        self.f.get_all.return_value = ['answer']

    def test_correction_copies_answers_links_and_arrival_without_modifying_original(self):
        revision = self.module.create_revision(self.source, self.task, 'Correct answers')
        self.assertEqual(revision.rework_of, 'source')
        self.assertEqual(revision.arrival_check_json, self.source.arrival_check_json)
        self.assertEqual(revision.qa_status, 'Pending')
        self.assertTrue(revision.flags.server_rework)
        self.assertEqual(self.created[1].answer_json, self.original.answer_json)
        self.assertEqual(self.created[1].evidence_links[0]['evidence'], 'photo')
        self.assertEqual(self.source.status, 'Submitted')
        self.assertNotEqual(revision.client_uuid, self.created[1].client_uuid)

    def test_revisit_starts_without_old_arrival_answers_or_evidence(self):
        revision = self.module.create_revision(self.source, self.task, 'Return to site')
        self.assertIsNone(revision.arrival_check_json)
        self.assertIsNone(revision.final_review_json)
        self.assertEqual(len(self.created), 1)

    def test_new_scout_revisit_never_copies_original_scout_answers_or_evidence(self):
        self.task.scout_profile = 'new-scout'
        revision = self.module.create_revision(self.source, self.task, 'Return to site')
        self.assertEqual(revision.agent, 'new-scout')
        self.assertEqual(revision.rework_of, 'source')
        self.assertIsNone(revision.arrival_check_json)
        self.assertEqual(len(self.created), 1)
        with self.assertRaisesRegex(ValueError, 'original scout'):
            self.module.create_revision(self.source, self.task, 'Correct answers')

    def test_assignment_choice_rejects_corrections_missing_reason_same_scout_and_unavailable_user(self):
        self.task.field_request = 'project'
        self.assertIsNone(self.module.validate_assignment(self.task, 'Correct answers'))
        for kind, scout, reason in [('Correct answers', 'new', 'Independent visit'), ('Return to site', 'new', ''), ('Return to site', 'scout', 'Unavailable')]:
            with self.assertRaises(ValueError):
                self.module.validate_assignment(self.task, kind, 'Assign another scout', scout, reason)
        profile = Record(name='new', user='new@example.com', availability_status='Available', check_permission=MagicMock())
        project = Record(check_permission=MagicMock())
        self.f.get_doc.side_effect = lambda dt, name: profile if dt == 'Scout Profile' else project
        self.f.db.get_value.return_value = True
        self.f.db.exists.return_value = False
        self.assertEqual(self.module.validate_assignment(self.task, 'Return to site', 'Assign another scout', 'new', 'Original scout unavailable'), 'new')
        project.check_permission.assert_called_with('write')
        self.f.db.exists.return_value = True
        with self.assertRaisesRegex(ValueError, 'active assignment'):
            self.module.validate_assignment(self.task, 'Return to site', 'Assign another scout', 'new', 'Unavailable')
        self.f.db.exists.return_value = False
        profile.availability_status = 'On Leave'
        with self.assertRaisesRegex(ValueError, 'available scout'):
            self.module.validate_assignment(self.task, 'Return to site', 'Assign another scout', 'new', 'Unavailable')
        profile.availability_status = 'Available'
        self.f.db.get_value.return_value = False
        with self.assertRaisesRegex(ValueError, 'enabled user'):
            self.module.validate_assignment(self.task, 'Return to site', 'Assign another scout', 'new', 'Unavailable')

    def test_replacement_preserves_original_owner_and_scope_then_cancels_old_task(self):
        self.task.field_request = 'project'
        self.task.questionnaire = 'questionnaire'
        self.task.questionnaire_scope = '["1.1"]'
        self.task.save = MagicMock()
        self.task.append = MagicMock()
        self.f.db.get_value.return_value = None
        self.module.create_revision = MagicMock(return_value=Record(name='blank-revisit'))
        replacement = self.module.create_replacement(self.task, self.source, 'new-scout', 'Original scout unavailable', ['1.1'], 'Verify the boundary')
        self.assertEqual(replacement.status, 'Assigned')
        self.assertEqual(replacement.scout_profile, 'new-scout')
        self.assertEqual(replacement.questionnaire_scope, self.task.questionnaire_scope)
        self.assertEqual(replacement.client_request_snapshot, self.task.client_request_snapshot)
        self.assertEqual(replacement.rework_count, 0, 'The receiving scout must not inherit a failure count')
        self.assertIsNone(replacement.accepted_at)
        self.assertEqual(replacement.replaces_task, self.task.name)
        self.assertEqual(self.task.replacement_task, replacement.name)
        self.assertEqual(self.task.status, 'Cancelled')
        self.assertEqual(self.task.scout_profile, 'scout')
        self.assertEqual(self.source.status, 'Submitted')
        self.task.append.assert_called_once()
        self.module.create_revision.assert_called_once_with(self.source, replacement, 'Return to site')

    def test_blank_server_revision_does_not_accept_assignment_for_new_scout(self):
        spec = importlib.util.spec_from_file_location('revision_start_test', ROOT / 'fieldpulse/fieldpulse/doctype/fp_task_response/fp_task_response.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.f,
            'frappe.model.document': types.SimpleNamespace(Document=object),
            'fieldpulse.utils': types.SimpleNamespace(haversine_distance_m=lambda *args: 0)}):
            spec.loader.exec_module(module)
        revision = Record(status='Draft', client_uuid='revision-uuid', task='replacement')
        self.f.flags.dd_rework_response_uuid = revision.client_uuid
        module.FPTaskResponse._sync_task_status(revision)
        self.f.get_doc.assert_not_called()
        # A later save by the scout follows the normal acceptance/start path.
        self.f.flags.dd_rework_response_uuid = None
        self.f.get_doc.return_value = Record(status='Assigned', name='replacement')
        self.f.get_doc.side_effect = None
        revision._transition_field_task = MagicMock(return_value=Record(status='Accepted'))
        module.FPTaskResponse._sync_task_status(revision)
        self.assertEqual([call.args[1] for call in revision._transition_field_task.call_args_list], ['Accepted', 'In Progress'])

    def test_revisit_rejects_old_or_missing_capture_times(self):
        response = Record(rework_type='Return to site', rework_of='source')
        self.f.db.get_value.return_value = '2026-10-24 12:00:00'
        for value in (None, '2026-10-24 11:59:59', '2026-10-24 12:00:00'):
            with self.assertRaisesRegex(ValueError, 'after the rework request'):
                self.module.require_fresh_capture(response, value)
        self.module.require_fresh_capture(response, '2026-10-24 12:00:01')

    def test_rework_requires_explicit_type_and_assigned_question_selection(self):
        submissions = types.SimpleNamespace(assigned_questions=lambda task: [Record(question_code='1.1')])
        visit = types.SimpleNamespace(strict=lambda task: True, verified_arrival=lambda doc, task: {'status': 'Inside'})
        with patch.dict(sys.modules, {'fieldpulse.scout_submissions': submissions, 'fieldpulse.scout_visit': visit}):
            for kind, codes in [('Unknown', ['1.1']), ('Correct answers', []), ('Correct answers', ['other']), ('Correct answers', {})]:
                with self.assertRaises(ValueError): self.module.validate_request(self.source, self.task, kind, codes)
            self.assertEqual(self.module.validate_request(self.source, self.task, 'Correct answers', ['1.1']), ['1.1'])
            visit.verified_arrival = lambda doc, task: {'status': 'Outside'}
            with self.assertRaisesRegex(ValueError, 'Return to site'): self.module.validate_request(self.source, self.task, 'Correct answers', ['1.1'])
            self.assertEqual(self.module.validate_request(self.source, self.task, 'Return to site', ['1.1']), ['1.1'])

    def test_evidence_reuse_is_limited_to_failed_ancestors_of_same_task_and_scout(self):
        original = Record(name='old', task='task', agent='scout', qa_status='Failed')
        revised = Record(name='new', task='task', agent='scout', rework_type='Correct answers', rework_of='old')
        documents = {'old': original, 'new': revised}
        get_doc = lambda dt, name: documents[name]
        self.assertTrue(evidence_origin_allowed('new', 'old', get_doc))
        for field, value in [('task', 'foreign'), ('agent', 'another'), ('qa_status', 'Passed')]:
            saved = original[field]; original[field] = value
            self.assertFalse(evidence_origin_allowed('new', 'old', get_doc)); original[field] = saved
        revised.rework_type = 'Return to site'
        self.assertFalse(evidence_origin_allowed('new', 'old', get_doc))
        revised.rework_type = 'Correct answers'; revised.rework_of = 'new'
        self.assertFalse(evidence_origin_allowed('new', 'old', get_doc))

    def test_review_rejects_second_decision_before_creating_another_revision(self):
        module = load('submission_review_tests', 'fieldpulse/scout_submissions.py', self.f)
        module.require_reviewer = lambda: None
        self.task.status = 'Submitted'
        self.f.get_doc.side_effect = lambda dt, name: self.source if dt == 'FP Task Response' else self.task
        self.f.db.get_value.return_value = None
        with self.assertRaisesRegex(ValueError, 'outstanding'):
            module.review_submission('source', 'Request rework', 'Fix the wall description', 'Correct answers', '["1.1"]')
        self.f.db.set_value.assert_not_called()

    def test_review_records_pending_revisit_without_creating_work_or_notifying_scout(self):
        review=load('pending_review_tests','fieldpulse/scout_submissions.py',self.f)
        review.require_reviewer=lambda:None
        self.source.qa_status='Pending';self.task.status='Submitted';self.task.save=MagicMock()
        self.f.db.get_value.return_value=None
        self.f.get_doc.side_effect=lambda dt,name:self.source if dt=='FP Task Response' else self.task
        self.module.validate_request=MagicMock(return_value=['1.1'])
        self.module.validate_assignment=MagicMock(return_value='new-scout')
        self.module.create_revision=MagicMock();self.module.create_replacement=MagicMock()
        pending=types.SimpleNamespace(create_request=MagicMock(return_value='revisit-request'))
        notifications=types.SimpleNamespace(queue_rework=MagicMock())
        with patch.dict(sys.modules,{'fieldpulse.scout_rework':self.module,'fieldpulse.revisit_authorization':pending,'fieldpulse.scout_notifications':notifications}):
            result=review.review_submission('source','Request rework','Verify the site','Return to site','["1.1"]','Assign another scout','new-scout','Unavailable')
        self.assertEqual(result['revisit_request'],'revisit-request')
        self.assertEqual(self.task.status,'Awaiting authorization')
        self.module.create_revision.assert_not_called();self.module.create_replacement.assert_not_called();notifications.queue_rework.assert_not_called()

    def test_report_is_prepared_only_after_every_active_task_is_approved(self):
        submissions = types.SimpleNamespace(require_reviewer=lambda: None, submission_detail=lambda response: {})
        with patch.dict(sys.modules, {'fieldpulse.scout_submissions': submissions}):
            module = load('report_readiness_tests', 'fieldpulse/scout_reports.py', self.f)
        module.prepare_report = MagicMock(return_value={'report': 'report'})
        self.f.get_all.side_effect = [['project'], [Record(status='Approved'), Record(status='In Progress')]]
        self.assertIsNone(module.prepare_if_ready('request'))
        module.prepare_report.assert_not_called()
        self.f.get_all.side_effect = [['project'], [Record(status='Approved'), Record(status='Approved')]]
        self.assertEqual(module.prepare_if_ready('request'), 'report')
        module.prepare_report.assert_called_once_with('request')


class NotificationTests(unittest.TestCase):
    def test_queue_is_durable_when_worker_enqueue_fails_and_duplicate_is_ignored(self):
        f = MagicMock()
        f.db.get_value.return_value = 'scout@example.com'
        f.db.exists.return_value = False
        f.enqueue.side_effect = RuntimeError('Redis unavailable')
        module = load('scout_notification_tests', 'fieldpulse/scout_notifications.py', f)
        task = Record(name='task', scout_profile='scout', task_number='TASK-1')
        key = module.queue_rework(task, Record(name='response'), 'Correct answers', ['1.1'], 'Clarify the finding')
        inserted = [call.args[0] for call in f.get_doc.call_args_list]
        self.assertEqual([row['doctype'] for row in inserted], ['Notification Log', 'DD Scout Notification'])
        self.assertEqual(inserted[1]['status'], 'Pending')
        f.db.exists.return_value = True
        self.assertEqual(module.queue_rework(task, Record(name='response'), 'Correct answers', ['1.1'], 'Clarify the finding'), key)
        self.assertEqual(f.get_doc.call_count, 2)


if __name__ == '__main__': unittest.main()
