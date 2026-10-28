import copy
import hashlib
import json
from pathlib import Path
import unittest
from fieldpulse.scout_library import evaluate
from fieldpulse.scout_protocol import arrival_result
from fieldpulse.scout_visit import sample_is_contemporaneous

ROOT=Path(__file__).parents[1]
SITE=dict(latitude=-1.3,longitude=36.8,geofence_radius_m=50)
POINT=dict(latitude=-1.3,longitude=36.8,accuracy_m=5,captured_at='2026-10-24T08:00:00Z')


def question(**config):
    base=dict(protocol_version=2,visit_workflow_version=2,group='service',answer_type='single',result_options=['Yes','No'],evidence=[])
    return dict(question_code='1.1',label='Plot check',validation_json=json.dumps(dict(base,**config)))


class VisitPolicyTests(unittest.TestCase):
    def test_shared_arrival_contract(self):
        data=json.loads((ROOT/'tests/fixtures/scout-visit-contract.json').read_text())
        for case in data['arrival_cases']:
            with self.subTest(case=case['name']):self.assertEqual(arrival_result(case['point'],data['site'],strict=True)['status'],case['status'])
    def test_legacy_testing_radius_never_unlocks_new_visit(self):
        distant=dict(POINT,latitude=-4.05,longitude=39.67)
        self.assertEqual(arrival_result(distant,SITE)['status'],'Inside')
        self.assertEqual(arrival_result(distant,SITE,strict=True)['status'],'Outside')
        self.assertEqual(arrival_result(POINT,SITE,strict=True)['radius_m'],50)

    def test_accuracy_missing_position_and_invalid_capture_time_do_not_verify(self):
        for changes in [dict(accuracy_m=100),dict(latitude=None),dict(captured_at='not-a-date')]:
            with self.subTest(changes=changes):self.assertNotEqual(arrival_result(dict(POINT,**changes),SITE,strict=True)['status'],'Inside')

    def test_explanation_or_forged_inside_status_cannot_bypass_arrival(self):
        result=evaluate([question()],{'1.1':dict(result='Yes')},{},dict(POINT,latitude=40,status='Inside',exception_reason='GPS trouble'),SITE)
        self.assertTrue(result['errors'])

    def test_failed_arrival_can_only_use_separate_review_route_without_answers(self):
        review=dict(visit_route='arrival_exception',arrival_exception_reason='Assigned gate cannot be located')
        result=evaluate([question()],{},{},{},SITE,review)
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['status'],'Needs review')
        self.assertIn('fieldwork has not been completed',' '.join(result['reasons']))
        self.assertTrue(evaluate([question()],{'1.1':dict(result='Yes')},{},{},SITE,review)['errors'])
        self.assertTrue(evaluate([question()],{},{},POINT,SITE,review)['errors'])

    def test_later_submission_uses_saved_arrival_not_current_position(self):
        result=evaluate([question()],{'1.1':dict(result='Yes')},{},POINT,SITE,dict(submission_latitude=40,submission_longitude=-74))
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['status'],'Submitted for normal review')

    def media(self,**values):
        return dict(name='photo',requirement_id='1.1::photo',evidence_type='Photo',caption='Automatic plot overview',metadata_origin='Camera',gps_lat=POINT['latitude'],gps_lng=POINT['longitude'],accuracy_m=5,captured_at='2026-10-24T08:01:00Z',location_sampled_at='2026-10-24T08:00:59Z',**values)

    def test_automatic_label_is_enough_for_routine_evidence(self):
        q=question(evidence=[dict(id='photo',kind='Photo',subject='Overview')])
        result=evaluate([q],{'1.1':dict(result='Yes')},{'1.1':[self.media()]},POINT,SITE)
        self.assertEqual(result['errors'],[])

    def test_issue_detail_can_be_in_finding_or_file_without_duplicate_caption(self):
        q=question(evidence=[dict(id='photo',kind='Photo',subject='Condition',detail_when=['Yes'])])
        args=([q],{'1.1':dict(result='Yes')},{'1.1':[self.media()]},POINT,SITE)
        self.assertTrue(evaluate(*args)['errors'])
        args[1]['1.1']['text']='Crack above kitchen window'
        self.assertEqual(evaluate(*args)['errors'],[])
        args[1]['1.1'].pop('text');args[2]['1.1'][0]['description']='Crack above kitchen window'
        self.assertEqual(evaluate(*args)['errors'],[])
        args[1]['1.1']['result']='No';args[2]['1.1'][0].pop('description')
        self.assertEqual(evaluate(*args)['errors'],[])

    def test_missing_or_stale_capture_gps_needs_explained_review_not_deleted_file(self):
        q=question(evidence=[dict(id='photo',kind='Photo',subject='Overview')])
        media=self.media();media['gps_lat']=None
        args=([q],{'1.1':dict(result='Yes')},{'1.1':[media]},POINT,SITE)
        self.assertTrue(evaluate(*args)['errors'])
        result=evaluate(*args,review=dict(capture_location_explanation='Indoor GPS unavailable'))
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['status'],'Needs review')
        self.assertEqual(result['summary'][0]['evidence'][0]['state'],'Attached')
        self.assertFalse(sample_is_contemporaneous('2026-10-24T08:01:00Z','2026-10-24T08:02:00Z'))
        self.assertFalse(sample_is_contemporaneous('2026-10-24T08:01:00Z','2026-10-24T07:58:00Z'))

    def test_imported_media_cannot_impersonate_camera_evidence(self):
        q=question(evidence=[dict(id='photo',kind='Photo',subject='Overview')])
        media=self.media();media['metadata_origin']='Imported document'
        self.assertTrue(evaluate([q],{'1.1':dict(result='Yes')},{'1.1':[media]},POINT,SITE)['errors'])

    def test_written_confirmation_does_not_need_photo_capture_gps(self):
        q=question(evidence=[dict(id='document',kind='Document',subject='Approved written confirmation')])
        media=dict(name='document',requirement_id='1.1::document',evidence_type='Document',caption='Institution confirmation',metadata_origin='Imported document')
        self.assertEqual(evaluate([q],{'1.1':dict(result='Yes')},{'1.1':[media]},POINT,SITE)['errors'],[])




if __name__=='__main__':unittest.main()
