import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).parents[1]
class Record(dict):
    def __getattr__(self,key):return self.get(key)
    def __setattr__(self,key,value):self[key]=value

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock();self.f.throw.side_effect=lambda msg,*args:(_ for _ in ()).throw(ValueError(msg))
        spec=importlib.util.spec_from_file_location('report_preparation_tests',ROOT/'fieldpulse/report_preparation.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.module)
        self.project=Record(name='project',project_title='House construction',field_brief='Check roof stage and visible cracks')
        mapping=dict(complete=True,reference='accepted-quote',version='2',scope=self.project.field_brief,
            checks=[dict(check_id='roof-check',customer_question='Has roofing started?',question_codes=['roof'])])
        self.task=Record(name='task',status='Approved',field_request='project',client_request_snapshot=json.dumps({'customer_coverage':mapping}))
        self.detail=dict(questions=[Record(name='q',question_code='roof',label='Has roofing started?',validation_json='{}')],
            answers=[Record(name='answer',question_code='roof',answer_json='{"result":"Observed","text":"Roof framing installed"}')],
            evidence=[Record(name='photo',evidence_type='Photo',caption='Roof framing',question_response='answer')],
            arrival={'status':'Inside','captured_at':'2026-10-25T08:00:00Z'},client_request={'questionnaire_review':{'scope_reference':'accepted-quote','scope_version':'2','scope':'Check roofing progress'},'site_reference':{'location_name':'Main house','address':'Agreed site'}},summary=[])
        self.f.get_all.side_effect=lambda dt,**kw:['project'] if dt=='Field Request' else [self.task]
        self.f.get_doc.side_effect=lambda dt,name:self.task if dt=='Field Task' else self.project
        self.f.db.get_value.return_value='approved-response'

    def content(self):
        with patch.dict(sys.modules,{'fieldpulse.scout_submissions':types.SimpleNamespace(submission_detail=lambda response:self.detail)}):
            return self.module.prepare_content('request')

    def test_draft_contains_actual_project_findings_scope_version_visit_and_unselected_media(self):
        content=self.content()
        self.assertIn('Roof framing installed',content['executive_summary'])
        self.assertEqual(content['report_checks'][0]['customer_question'],'Has roofing started?')
        self.assertEqual(json.loads(content['scope_snapshot_json'])[0]['version'],'2')
        self.assertEqual(json.loads(content['visit_snapshot_json'])[0]['site'],'Main house')
        self.assertEqual(content['report_evidence'][0]['include_client'],0)
        self.assertTrue(json.loads(content['coverage_snapshot_json'])['complete'])

    def test_questionnaire_report_needs_no_separate_customer_mapping(self):
        self.task.client_request_snapshot='{}'
        content=self.content()
        self.assertTrue(json.loads(content['coverage_snapshot_json'])['complete'])
        self.assertEqual(content['report_checks'][0]['assessment'],'Supported finding')

    def test_missing_verified_visit_cannot_become_a_supported_finding(self):
        self.detail['arrival']={}
        row=self.content()['report_checks'][0]
        self.assertEqual(row['assessment'],'Not verified')
        self.assertIn('verified arrival',row['limitations'])

    def test_report_uses_assigned_questions_even_when_historical_mapping_says_something_else(self):
        self.task.client_request_snapshot=json.dumps({'customer_coverage':{'complete':False,'checks':[{'customer_question':'Old unrelated boundary question','question_codes':['boundary']}]}})
        self.detail['questions'].append(Record(name='missing',question_code='cracks',label='Are cracks visible?',validation_json='{}'))
        self.detail['questions'].append(Record(name='opening',question_code='S1',label='Assigned site?',validation_json='{"group":"shared"}'))
        content=self.content()
        self.assertEqual([row['customer_question'] for row in content['report_checks']],['Has roofing started?','Are cracks visible?'])
        self.assertEqual(content['report_checks'][1]['assessment'],'Not verified')
        self.assertNotIn('Old unrelated boundary question',content['findings'])

    def test_pdf_only_references_evidence_selected_for_client_release(self):
        content=self.content()
        doc=Record(content);doc.report_checks=[Record(row) for row in doc.report_checks]
        context=self.module.pdf_context(doc,[])
        self.assertEqual(context['checks'][0]['evidence_refs'],[])
        context=self.module.pdf_context(doc,[(Record(),Record(name='photo'))])
        self.assertEqual(context['checks'][0]['evidence_refs'],['E001'])

if __name__=='__main__':unittest.main()
