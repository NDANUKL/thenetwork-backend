import copy
import hashlib
import json
from pathlib import Path
import unittest
from fieldpulse.scout_library import (evaluate_question, resolve_config, validate_config,
    required_evidence, needs_source_basis)

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

    def test_explicit_source_basis_overrides_legacy_source_requirement(self):
        config = dict(FIXTURES['base'], source_basis_required=True, source_required=True,
                      answer_type='single', result_options=['Reported available'], evidence=[])
        answer = dict(result='Reported available', text='Observed on site', source_type='Direct observation')
        self.assertEqual(evaluate_question('12.1', config, answer, {}, [])['errors'], [])
        for source in ['Representative', 'Document or record', 'Combination']:
            answer['source_type'] = source
            self.assertTrue(any('source' in error for error in evaluate_question('12.1', config, answer, {}, [])['errors']))


    def test_unavailable_item_does_not_require_impossible_reading(self):
        config = dict(protocol_version=2, group='service', answer_type='checklist', result_options=['Observed','Unable to inspect'], evidence=[], items=[dict(id='meter',label='Meter',reading_required=True,quantity_required=True)])
        answer = dict(items=dict(meter=dict(result='Unable to inspect', explanation='Access refused')))
        self.assertEqual(evaluate_question('5.2',config,answer,{},[])['errors'], [])

    def test_quantity_format_matches_mobile(self):
        config = dict(protocol_version=2,group='service',answer_type='checklist',result_options=['Present'],evidence=[],items=[dict(id='goods',label='Goods',quantity_required=True)])
        for quantity in ['0','2.5','1e3',' 3 ']:
            self.assertEqual(evaluate_question('13.1',config,dict(items=dict(goods=dict(result='Present',quantity=quantity))),{},[])['errors'], [])
        for quantity in [' ','-1','NaN','Infinity','0x10','1_000']:
            self.assertTrue(any('quantity' in error for error in evaluate_question('13.1',config,dict(items=dict(goods=dict(result='Present',quantity=quantity))),{},[])['errors']))

    def test_unavailable_outcomes_ignore_inactive_followups(self):
        config = dict(protocol_version=2,group='service',answer_type='checklist',result_options=['Present','Unable to check','Not found'],source_basis_required=True,source_required=True,condition=True,identifier=True,demonstration=True,evidence=[],items=[dict(id='pump',label='Pump',quantity_required=True,reading_required=True,demonstration_required=True,video_demonstration_required=True)])
        answer = dict(items=dict(pump=dict(result='Unable to check',text='Access refused',quantity='bad',condition='Visible damage or deterioration',identifier='Identifier differs',demonstration='Demonstrated with an issue')))
        self.assertEqual(evaluate_question('2.4',config,answer,{},[])['errors'], [])
        self.assertEqual(required_evidence('2.4',config,answer), [])
        answer['items']['pump'] = dict(result='Not found',text='Checked the assigned room; pump absent')
        answer['source_type'] = 'Direct observation'
        self.assertEqual(evaluate_question('2.4',config,answer,{},[])['errors'], [])

    def test_no_record_still_needs_office_but_unreachable_does_not(self):
        config = dict(protocol_version=2,group='service',answer_type='single',result_options=['No matching record found','Issuer could not be reached'],source_required=True,evidence=[])
        self.assertTrue(any('source office' in error for error in evaluate_question('12.1',config,dict(result='No matching record found',text='Office searched the supplied receipt reference'),{},[])['errors']))
        self.assertEqual(evaluate_question('12.1',config,dict(result='Issuer could not be reached',text='Office closed; contact did not answer',source_type='Representative'),{},[])['errors'], [])


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
