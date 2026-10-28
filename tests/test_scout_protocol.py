import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


def load(name, path, modules=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules or {}): spec.loader.exec_module(module)
    return module


protocol = load('scout_protocol_test', 'fieldpulse/scout_protocol.py')


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.radius_patch = patch.dict(protocol.effective_geofence_radius.__globals__, TESTING_GEOFENCE_RADIUS_M=0)
        self.radius_patch.start()
        self.addCleanup(self.radius_patch.stop)
        self.question = dict(name='q', question_code='1.4', validation_json=json.dumps(dict(group='service', mandatory_evidence=True)))
        self.answer = dict(result='Observed', text='No construction activity observed.', media=[])
        self.media = [{'evidence_type': kind, 'caption': kind + ' showing the visible plot.'} for kind in ['Photo', 'Video']]
        self.review = dict(coverage='Yes')

    def evaluate(self, **kw):
        values = dict(questions=[self.question], answers={'1.4': self.answer}, evidence={'1.4': self.media}, review=self.review, arrival={'status': 'Inside'})
        values.update(kw)
        return protocol.evaluate_submission(**values)

    def test_home_submission_uses_saved_arrival_and_capture_not_current_location(self):
        site = dict(latitude=-1.3, longitude=36.8, geofence_radius_m=50)
        media = [dict(row, gps_lat=-1.3, gps_lng=36.8, accuracy_m=8, captured_at='2026-10-20T07:00:00Z') for row in self.media]
        result = self.evaluate(evidence={'1.4': media}, location=site)
        self.assertFalse(result['errors'])
        self.assertEqual(result['status'], 'Submitted for normal review')

    def test_offsite_or_missing_capture_location_needs_explained_review(self):
        site = dict(latitude=-1.3, longitude=36.8, geofence_radius_m=50)
        for fields in [dict(gps_lat=-1.4, gps_lng=36.8, accuracy_m=8, captured_at='2026-10-20T07:00:00Z'), {}, dict(gps_lat=-1.3, gps_lng=36.8, accuracy_m=100, captured_at='2026-10-20T07:00:00Z')]:
            media = [dict(row, **fields) for row in self.media]
            self.assertTrue(self.evaluate(evidence={'1.4':media}, location=site)['errors'])
            result = self.evaluate(evidence={'1.4':media}, location=site, review=dict(coverage='Yes', incomplete=True, incomplete_reason='GPS was unreliable during the visit.'))
            self.assertFalse(result['errors'])
            self.assertEqual(result['status'], 'Needs review')
            self.assertTrue(any('capture location requires review' in reason for reason in result['reasons']))

    def test_testing_radius_allows_cross_county_arrival_and_evidence(self):
        site = dict(latitude=-1.3, longitude=36.8, geofence_radius_m=50)
        point = dict(latitude=-4.05, longitude=39.67, accuracy_m=8, captured_at='2026-10-23T15:00:00Z')
        media = [dict(row, gps_lat=point['latitude'], gps_lng=point['longitude'], accuracy_m=8, captured_at=point['captured_at']) for row in self.media]
        with patch.dict(protocol.effective_geofence_radius.__globals__, TESTING_GEOFENCE_RADIUS_M=2_000_000):
            arrival = protocol.arrival_result(point, site)
            self.assertEqual(arrival['status'], 'Inside')
            self.assertFalse(self.evaluate(evidence={'1.4': media}, location=site, arrival=arrival)['errors'])
            self.assertEqual(protocol.arrival_result(dict(point, accuracy_m=70), site)['status'], 'Insufficient accuracy')

    def test_frappe_location_document_supports_arrival_and_uploaded_media(self):
        class LocationDocument:
            # Frappe documents expose get(), rather than dictionary subscripting.
            def get(self, key):
                return dict(latitude=-1.3, longitude=36.8, geofence_radius_m=50).get(key)
        site = LocationDocument()
        point = dict(latitude=-1.3, longitude=36.8, accuracy_m=8, captured_at='2026-10-23T15:00:00Z')
        arrival = protocol.arrival_result(point, site)
        self.assertEqual(arrival['status'], 'Inside')
        media = [dict(row, gps_lat=point['latitude'], gps_lng=point['longitude'], accuracy_m=8, captured_at=point['captured_at']) for row in self.media]
        result = self.evaluate(evidence={'1.4': media}, location=site, arrival=arrival)
        self.assertFalse(result['errors'])
        self.assertEqual(result['status'], 'Submitted for normal review')
        missing_site = type('MissingLocationDocument', (), {'get': lambda self, key: None})()
        self.assertEqual(protocol.arrival_result(point, missing_site)['status'], 'Invalid GPS')

    def test_rejection_names_missing_evidence(self):
        errors = self.evaluate(evidence={})['errors']
        self.assertTrue(any('1.4: mandatory photo and caption missing' in error for error in errors))

    def test_verified_photo_and_video_allow_normal_review_not_automatic_approval(self):
        result = self.evaluate()
        self.assertEqual(result, {'errors': [], 'reasons': [], 'status': 'Submitted for normal review'})

    def test_missing_either_medium_cannot_be_normal_completion(self):
        for kind in ['Photo', 'Video']:
            result = self.evaluate(evidence={'1.4': [row for row in self.media if row['evidence_type'] != kind]})
            self.assertTrue(result['errors'])
            self.assertTrue(any('mandatory ' + kind.lower() in r for r in result['reasons']))

    def test_missing_media_is_reportable_as_incomplete_with_reason(self):
        result = self.evaluate(evidence={}, review=dict(coverage='Partly', additional_text='Access to the north section was denied; arrange entry.', incomplete=True, incomplete_reason='Recording permission declined.'))
        self.assertFalse(result['errors'])
        self.assertEqual(result['status'], 'Needs review')
        self.assertGreaterEqual(len(result['reasons']), 4)

    def test_upload_without_caption_does_not_count(self):
        result = self.evaluate(evidence={'1.4': [dict(row, caption='') for row in self.media]})
        self.assertTrue(result['errors'])

    def test_partly_and_no_require_explanation(self):
        for value in ['Partly', 'No']:
            self.assertTrue(self.evaluate(review=dict(coverage=value))['errors'])

    def test_yes_with_unresolved_check_is_rejected(self):
        answer = dict(result='Unable to check', text='Entrance blocked', explanation='No access; arrange a return visit.')
        self.assertTrue(any('unresolved' in e for e in self.evaluate(answers={'1.4': answer})['errors']))

    def test_not_applicable_does_not_automatically_fail_whole_request(self):
        answer = dict(result='Not applicable', text='There is no building on this plot.', explanation='The agreed question concerned the open plot.')
        self.assertFalse(self.evaluate(answers={'1.4': answer})['errors'])

    def test_conditionals_require_attribution_and_concern_details(self):
        answer = dict(self.answer, information_source=True, concern=True)
        issues = protocol.answer_issues(self.question, answer, self.media)
        self.assertTrue(any('source role' in e for e in issues))
        self.assertTrue(any('description and location' in e for e in issues))

    def test_demonstration_is_not_implied_by_presence(self):
        q = dict(self.question, validation_json=json.dumps(dict(demonstration_required=True)))
        self.assertTrue(protocol.answer_issues(q, self.answer, []))
        self.assertFalse(protocol.answer_issues(q, dict(self.answer, demonstration='Not demonstrated'), []))

    def test_final_card_needs_explicit_coverage_selection(self):
        self.assertTrue(self.evaluate(review={})['errors'])

    def test_arrival_gate_checks_accuracy_radius_and_real_coordinates(self):
        site = dict(latitude=-1.3, longitude=36.8, geofence_radius_m=50)
        point = dict(latitude=-1.3, longitude=36.8, accuracy_m=8, captured_at='2026-10-20T07:00:00Z')
        self.assertEqual(protocol.arrival_result(point, site)['status'], 'Inside')
        self.assertEqual(protocol.arrival_result(dict(point, accuracy_m=60), site)['status'], 'Insufficient accuracy')
        self.assertEqual(protocol.arrival_result(dict(point, latitude=-1.4), site)['status'], 'Outside')
        self.assertEqual(protocol.arrival_result(dict(point, accuracy_m=None), site)['status'], 'Invalid GPS')
        self.assertEqual(protocol.arrival_result(dict(point, latitude=float('nan')), site)['status'], 'Invalid GPS')

    def test_incomplete_location_issue_retains_all_reasons(self):
        result = self.evaluate(answers={}, evidence={}, arrival={'status': 'Invalid GPS'}, review=dict(coverage='No', additional_text='Unable to start. GPS permission denied.', incomplete=True, incomplete_reason='Device location unavailable; arrange a return visit.'))
        self.assertFalse(result['errors'])
        self.assertTrue(any('Arrival location' in e for e in result['reasons']))




class PermissionTests(unittest.TestCase):
    def test_scout_cannot_read_another_assignees_submission(self):
        api = MagicMock()
        api.get_roles.return_value = ['Field Agent']
        api.db.exists.return_value = 'scout-a'
        api.db.get_value.return_value = 'scout-b'
        module = load('scout_permissions_test', 'fieldpulse/scout_permissions.py', {'frappe': api})
        self.assertFalse(module.record_permission(types.SimpleNamespace(doctype='FP Task Response', task='task', agent='scout-a')))
        api.db.get_value.return_value = 'scout-a'
        self.assertIsNone(module.record_permission(types.SimpleNamespace(doctype='FP Task Response', task='task', agent='scout-a')))


if __name__ == '__main__': unittest.main()
