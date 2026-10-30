import copy
import json
from pathlib import Path
import unittest

from fieldpulse.task_briefs import validate_brief, brief_digest, assigned_brief, gps_result, evaluate_submission

FIXTURE = Path(__file__).parent / 'fixtures/task-brief-v1.json'


class TaskBriefTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.brief = self.data['brief']

    def evaluate(self, submission=None, evidence=None):
        return evaluate_submission(self.brief, ['condition'], submission or self.data['submission'],
            self.data['evidence'] if evidence is None else evidence,
            task_id='TASK-1', scout_id='SCOUT-1', site=self.data['site'])

    def test_complete_is_never_verified(self):
        result = self.evaluate()
        self.assertTrue(result['complete'])
        self.assertFalse(result['verified'])
        self.assertEqual(result['status'], 'pending_coordinator_review')

    def test_counts_and_metadata_are_required(self):
        self.assertFalse(self.evaluate(evidence=self.data['evidence'][:1])['complete'])
        for field, value in [('task_id', 'OTHER'), ('scout_id', 'OTHER'), ('check_id', 'OTHER'),
                             ('source', 'unknown'), ('captured_at', 'bad'),
                             ('uploaded', False), ('file_id', None)]:
            with self.subTest(field=field):
                rows = copy.deepcopy(self.data['evidence'])
                rows[0][field] = value
                self.assertFalse(self.evaluate(evidence=rows)['complete'])

    def test_capture_gps_uncertainty_counts_but_requires_review(self):
        for change in [dict(accuracy_m=200), dict(latitude=0),
                       dict(location_sampled_at='2026-10-28T07:00:00Z')]:
            with self.subTest(change=change):
                rows = copy.deepcopy(self.data['evidence'])
                rows[0].update(change)
                result = self.evaluate(evidence=rows)
                self.assertTrue(result['complete'])
                self.assertFalse(result['verified'])
                self.assertTrue(any('coordinator review required' in flag for flag in result['flags']))

    def test_gallery_photo_counts_as_unverified_fallback_only(self):
        rows = copy.deepcopy(self.data['evidence'])
        rows[0].update(source='gallery', captured_at=None, latitude=None, longitude=None,
                       accuracy_m=None, location_sampled_at=None)
        result = self.evaluate(evidence=rows)
        self.assertTrue(result['complete'])
        self.assertFalse(result['verified'])
        self.assertTrue(any('Gallery photo' in flag for flag in result['flags']))
        video_brief = copy.deepcopy(self.brief)
        video_brief['checks'][0]['evidence'] = [dict(kind='video', minimum=2, instruction='Record the required views.')]
        video_rows = copy.deepcopy(rows)
        for row in video_rows:
            row.update(kind='video', source='gallery', captured_at=None, latitude=None, longitude=None,
                       accuracy_m=None, location_sampled_at=None)
        video_result = evaluate_submission(video_brief, ['condition'], self.data['submission'], video_rows,
            task_id='TASK-1', scout_id='SCOUT-1', site=self.data['site'])
        self.assertTrue(video_result['complete'])
        self.assertTrue(any('Gallery video' in flag for flag in video_result['flags']))

    def test_missing_capture_location_is_nonblocking_and_flagged(self):
        rows = copy.deepcopy(self.data['evidence'])
        for row in rows:
            row.update(latitude=None, longitude=None, accuracy_m=None, location_sampled_at=None)
        result = self.evaluate(evidence=rows)
        self.assertTrue(result['complete'])
        self.assertFalse(result['verified'])
        self.assertTrue(any('Location unavailable' in flag for flag in result['flags']))

    def test_interrupted_visit_preserves_partial_work_without_completing_checks(self):
        submission = copy.deepcopy(self.data['submission'])
        submission['access_issue'] = 'Site manager stopped the visit'
        result = self.evaluate(submission, self.data['evidence'][:1])
        self.assertTrue(result['complete'])
        self.assertEqual(result['status'], 'access_issue')
        self.assertFalse(result['verified'])
        self.assertEqual(result['checks'], [])
        foreign = copy.deepcopy(self.data['evidence'][:1])
        foreign[0]['scout_id'] = 'OTHER'
        self.assertFalse(self.evaluate(submission, foreign)['complete'])

    def test_duplicate_media_does_not_satisfy_counts(self):
        self.assertFalse(self.evaluate(evidence=[self.data['evidence'][0]] * 2)['complete'])
        rows = copy.deepcopy(self.data['evidence'])
        rows[1]['file_id'] = rows[0]['file_id']
        self.assertFalse(self.evaluate(evidence=rows)['complete'])

    def test_unable_is_complete_but_distinct_and_needs_reason(self):
        submission = copy.deepcopy(self.data['submission'])
        submission['answers']['condition'] = {'status': 'unable_to_verify', 'explanation': 'Access refused'}
        result = self.evaluate(submission, [])
        self.assertTrue(result['complete'])
        self.assertEqual(result['checks'][0]['status'], 'unable_to_verify')
        submission['answers']['condition']['explanation'] = ''
        self.assertFalse(self.evaluate(submission, [])['complete'])

    def test_safe_access_exception_never_becomes_fieldwork(self):
        submission = dict(answers={}, arrival={}, access_issue='Unsafe approach', declaration=True)
        result = self.evaluate(submission, [])
        self.assertTrue(result['complete'])
        self.assertEqual(result['status'], 'access_issue')
        self.assertTrue(result['flags'])
        self.assertFalse(self.evaluate(submission)['complete'])

    def test_arrival_and_declaration_gate_completion(self):
        for change in ({'arrival': {}}, {'declaration': False}):
            self.assertFalse(self.evaluate(dict(self.data['submission'], **change))['complete'])

    def test_approval_digest_changes_for_reordered_or_edited_checks(self):
        before = brief_digest(self.brief)
        edited = copy.deepcopy(self.brief)
        edited['objective'] = 'Changed scope'
        self.assertNotEqual(before, brief_digest(edited))
        self.assertEqual(before, brief_digest(json.dumps(self.brief)))

    def test_no_category_templates_or_unknown_categories(self):
        for category in ['land_property_check', 'construction_progress', 'business_asset_check', 'custom_ground_verification']:
            self.assertEqual(validate_brief(dict(self.brief, category=category))['checks'], self.brief['checks'])
        with self.assertRaises(ValueError):
            validate_brief(dict(self.brief, category='Land or plot check'))

    def test_scope_is_independent_per_scout(self):
        with self.assertRaises(ValueError):
            assigned_brief(self.brief, ['unknown'])
        with self.assertRaises(ValueError):
            assigned_brief(self.brief, ['condition', 'condition'])
        submission = dict(self.data['submission'], answers={'other_scout_check': {}})
        with self.assertRaises(ValueError):
            self.evaluate(submission)

    def test_gps_uses_separate_accuracy_threshold(self):
        point = dict(self.data['submission']['arrival'], accuracy_m=30)
        self.assertEqual(gps_result(point, self.data['site'])['status'], 'inaccurate')
        self.assertEqual(gps_result(dict(point, accuracy_m=5, latitude=0), self.data['site'])['status'], 'outside')

    def test_no_checks_only_allowed_for_review(self):
        with self.assertRaises(ValueError):
            validate_brief(dict(self.brief, checks=[]))
        self.assertEqual(validate_brief(dict(self.brief, checks=[], review_required=True, review_reasons=['Unclear request']))['checks'], [])


if __name__ == '__main__':
    unittest.main()
