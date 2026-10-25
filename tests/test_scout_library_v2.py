import copy
import hashlib
import json
from pathlib import Path
import unittest
from fieldpulse.scout_library import (evaluate_question, resolve_config, validate_config,
    required_evidence, SHARED_V2, CLOSING_V2)

ROOT = Path(__file__).parents[1]
FIXTURES = json.loads((ROOT / 'tests/fixtures/scout-v2-contract.json').read_text())


class LibraryContractTests(unittest.TestCase):
    def test_shared_python_typescript_contract(self):
        for case in FIXTURES['cases']:
            with self.subTest(case=case['name']):
                code = case.get('code', '1.1')
                config = dict(FIXTURES['base'], **case.get('config', {}))
                answer = case['answer']
                bank = {m['attachment_id']:m for m in case.get('bank', [])}
                evidence = [dict(requirement_id=link['requirement_id'], evidence_type=bank[link['attachment_id']]['kind'], caption=bank[link['attachment_id']]['caption']) for link in answer.get('evidence_links', []) if link['attachment_id'] in bank]
                result = evaluate_question(code, config, answer, dict(case.get('answers', {}), **{code:answer}), evidence)
                self.assertEqual(not result['errors'], case['valid'], result)
                if 'review' in case: self.assertEqual(bool(result['reasons']), case['review'])
                if 'states' in case: self.assertEqual([r['state'] for r in result['evidence']], case['states'])
                if 'skipped' in case: self.assertEqual(result['skipped'], case['skipped'])

    def test_catalogue_matches_retained_source_and_has_all_services(self):
        data = json.loads((ROOT / 'fieldpulse/configuration/scout-questionnaires-v2.json').read_text(encoding='utf-8'))
        self.assertEqual(data['source_sha256'], hashlib.sha256((ROOT / 'docs/scout-questionnaire-library.md').read_bytes()).hexdigest())
        self.assertEqual([len(s['questions']) for s in data['services']], [3,4,5,4,3,3,2,2,2,2,2,2,4,1,4])
        for service in data['services']:
            for q in service['questions']:
                validate_config(dict(q, protocol_version=2))
                self.assertNotIn('mandatory_evidence', q)

    def test_configuration_cannot_override_protocol_or_leave_media_unspecified(self):
        base = dict(FIXTURES['base'])
        with self.assertRaises(ValueError): resolve_config(base, {'protocol_version':1})
        with self.assertRaises(ValueError): validate_config(dict(base, evidence=None))
        with self.assertRaises(ValueError): resolve_config(dict(base, answer_type='checklist'), {})
        with self.assertRaises(ValueError): resolve_config(dict(base, evidence=[dict(id='x',kind='Photo',subject='')]), {})

    def test_confirmation_method_is_explicit_and_verbal_needs_no_media(self):
        base = dict(FIXTURES['base'], confirmation=True)
        with self.assertRaises(ValueError): resolve_config(base, {})
        self.assertEqual(resolve_config(base, {'confirmation_method':'Verbal'})['evidence'], [])
        written = resolve_config(base, {'confirmation_method':'Written','confirmation_subject':'Approved enrolment confirmation'})
        self.assertEqual(written['evidence'][0]['kind'], 'Document')
        with self.assertRaises(ValueError): resolve_config(base, {'confirmation_method':'Authorised photo'})

    def test_custom_question_requires_explicit_capture_policy(self):
        base = dict(FIXTURES['base'], answer_type='custom')
        with self.assertRaises(ValueError): resolve_config(base, {'items':[dict(id='x',label='Check pump')]})
        self.assertEqual(resolve_config(base, {'items':[dict(id='x',label='Check pump',evidence=[])]})['items'][0]['evidence'], [])

    def test_confirmation_remains_required_if_later_fields_were_confirmed(self):
        config = resolve_config(dict(FIXTURES['base'], answer_type='checklist', result_options=['Matches','Not confirmed'], confirmation=True), {'items':[dict(id='a',label='Date'),dict(id='b',label='Amount')], 'confirmation_method':'Written','confirmation_subject':'Approved payment confirmation'})
        answer = dict(items={'a':dict(result='Not confirmed',text='Not available'), 'b':dict(result='Matches')})
        self.assertEqual([r['requirement_id'] for r in required_evidence('8.2',config,answer)], ['8.2::confirmation'])

    def test_walkthrough_is_once_and_demo_video_only_for_demonstrated_functions(self):
        base = dict(FIXTURES['base'], answer_type='checklist', demonstration=True)
        config = resolve_config(base, {'items':[dict(id='a',label='Pump',demonstration_required=True,video_demonstration_required=True),dict(id='b',label='Generator')], 'walkthrough_subject':'Cover the assigned work areas'})
        answer = dict(items={'a':dict(result='Yes',demonstration='Not demonstrated',text='No power'), 'b':dict(result='Yes')})
        self.assertEqual([r['kind'] for r in required_evidence('1.1',config,answer)], ['Video'])
        answer['items']['a']['demonstration'] = 'Demonstrated without an obvious issue'
        self.assertEqual([r['kind'] for r in required_evidence('1.1',config,answer)], ['Video','Video'])

    def test_unverified_capture_requires_explanation_and_remains_flagged(self):
        from fieldpulse.scout_library import evaluate
        question = dict(question_code='1.1',label='Overview',validation_json=json.dumps(dict(FIXTURES['base'], evidence=[dict(id='photo',kind='Photo',subject='Overview')])))
        evidence = {'1.1':[dict(name='file',evidence_type='Photo',caption='Overview',requirement_id='1.1::photo')]}
        args = ([question], {'1.1':dict(result='Yes')}, evidence, dict(status='Inside'), dict(latitude=1,longitude=1))
        self.assertTrue(evaluate(*args)['errors'])
        explained = evaluate(*args, review=dict(capture_location_explanation='Camera location permission failed'))
        self.assertEqual(explained['errors'],[])
        self.assertEqual(explained['status'],'Needs review')


if __name__ == '__main__': unittest.main()
