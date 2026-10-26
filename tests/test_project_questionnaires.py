import copy
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from fieldpulse import project_questionnaires as editor
from fieldpulse.scout_library import evaluate_question


class Record(dict):
    def __getattr__(self,key):return self.get(key)
    def __setattr__(self,key,value):self[key]=value


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.boundary=Record(name='boundary',question_code='1.2',label='What boundaries are visible?',validation_json=json.dumps(dict(group='service',protocol_version=1)))
        self.media=Record(name='media',question_code='1.4',label='Record visible site conditions',validation_json=json.dumps(dict(group='service',protocol_version=1,mandatory_evidence=True)))
        self.questions=[self.boundary,self.media]
        self.project=Record(name='project',project_title='Maize harvest',field_brief='Check whether maize was harvested.',scout_questionnaire='base',scout_service='Land or plot check',
            scout_checks=[Record(question='media',label='Photograph the maize and field',check_key='media-check',evidence_mode='Specify evidence',
                evidence_json=json.dumps([dict(id='visit-photo',kind='Photo',subject='Photograph maize and field'),dict(id='visit-video',kind='Video',subject='Show the field condition')])),
                Record(question=None,label='What proportion of maize appears harvested?',check_key='maize-check',answer_format='Single choice',
                    answer_options='Standing\nPartly harvested\nFully harvested\nUnable to establish',evidence_mode='Specify evidence',evidence_json='[]')])

    def test_incomplete_template_settings_remain_editable(self):
        source=Record(name='interview',questionnaire='base',label='What is offered?',
            validation_json=json.dumps(dict(group='service',protocol_version=2,
                answer_type='interview',result_options=['Confirmed'],confirmation=True,evidence=[])))
        project=Record(scout_questionnaire='base',scout_checks=[Record(question='interview')])
        project.check_permission=MagicMock()
        fake=MagicMock()
        fake.get_doc.side_effect=[project,source]
        with patch.dict(sys.modules,{'frappe':fake}):
            settings=editor.editor_settings('project','interview')
        self.assertTrue(settings['configuration_template']['confirmation'])
        self.assertEqual(settings['evidence'],[])
        self.assertEqual(settings['options'],['Confirmed'])

    def test_incomplete_check_error_identifies_the_question(self):
        self.boundary.validation_json=json.dumps(dict(group='service',protocol_version=2,
            answer_type='checklist',result_options=['Confirmed'],evidence=[]))
        self.project.scout_checks.insert(0,Record(question='boundary',label='Which boundary markers exist?'))
        with self.assertRaisesRegex(ValueError,'Which boundary markers exist.*Edit question and evidence'):
            editor.build_specs(self.project,self.questions)

    def test_custom_question_and_wording_replace_irrelevant_template_questions(self):
        original=copy.deepcopy(self.questions)
        editor.validate_draft(self.project,self.questions)
        specs=editor.build_specs(self.project,self.questions)
        self.assertEqual([row['code'] for row in specs[:2]],['S1','S2'])
        self.assertEqual(specs[-1]['code'],'S_EXTRA')
        self.assertNotIn(self.boundary.label,[row['label'] for row in specs])
        self.assertIn('Photograph the maize and field',[row['label'] for row in specs])
        custom=next(row for row in specs if row['code'].startswith('P_'))
        self.assertEqual(custom['config']['result_options'][2],'Fully harvested')
        self.assertEqual(custom['config']['answer_type'],'single')
        self.assertTrue(editor.has_edits(self.project,self.questions))
        self.assertEqual(self.questions,original,'Source questions must not be modified')

    def test_required_visit_evidence_cannot_be_deleted_or_weakened(self):
        self.project.scout_checks[0].evidence_json='[]'
        with self.assertRaisesRegex(ValueError,'protected required media'):editor.build_specs(self.project,self.questions)
        self.project.scout_checks=self.project.scout_checks[1:]
        with self.assertRaisesRegex(ValueError,'required visit-evidence'):editor.build_specs(self.project,self.questions)

    def test_answer_choices_and_evidence_conditions_are_validated_before_dispatch(self):
        self.project.scout_checks[1].answer_options='Standing\nStanding'
        with self.assertRaisesRegex(ValueError,'unique answer choices'):editor.build_specs(self.project,self.questions)
        self.project.scout_checks[1].answer_options='Standing\nHarvested'
        self.project.scout_checks[1].evidence_json=json.dumps([dict(kind='Photo',subject='Crop',when=['Not an allowed answer'])])
        with self.assertRaisesRegex(ValueError,'allowed answers'):editor.build_specs(self.project,self.questions)

    def test_service_authorization_survives_replacing_service_questions(self):
        config=json.loads(self.boundary.validation_json);config['authorisation_required']=True
        self.boundary.validation_json=json.dumps(config)
        with self.assertRaisesRegex(ValueError,'authorization'):editor.build_specs(self.project,self.questions)
        self.project.scout_authorisation='Permission confirmed with site representative'
        for row in editor.build_specs(self.project,self.questions):
            if row['config']['group']=='service':self.assertTrue(row['config']['authorisation_required'])

    def test_fingerprint_changes_for_text_order_or_evidence_edits(self):
        before=editor.fingerprint(self.project)
        self.project.scout_checks[1].label='Has maize harvesting finished?'
        self.assertNotEqual(before,editor.fingerprint(self.project))
        before=editor.fingerprint(self.project);self.project.scout_checks.reverse()
        self.assertNotEqual(before,editor.fingerprint(self.project))

    def test_source_basis_is_recorded_in_the_answer_not_invented_in_the_report(self):
        config=next(row['config'] for row in editor.build_specs(self.project,self.questions) if row['code'].startswith('P_'))
        answer=dict(result='Fully harvested',text='Cut stalks and harvested rows are visible.')
        self.assertTrue(evaluate_question('P_maize',config,answer,{},[])['errors'])
        answer['source_type']='Direct observation'
        self.assertEqual(evaluate_question('P_maize',config,answer,{},[])['errors'],[])
        answer['source_type']='Representative'
        self.assertTrue(evaluate_question('P_maize',config,answer,{},[])['errors'])
        answer['source_role']='Site caretaker'
        self.assertEqual(evaluate_question('P_maize',config,answer,{},[])['errors'],[])

    def test_materialized_versions_are_project_only_immutable_and_retry_safe(self):
        store={('FP Questionnaire','base'):Record(name='base',service_code='land',source_sha256='source',version=1)}
        f=MagicMock();created=[]
        def get_doc(kind,name=None):
            if isinstance(kind,str):return store[(kind,name)]
            doc=Record(kind)
            def insert(**kwargs):
                doc.name=kwargs.get('set_name') or 'question-'+str(len(created))
                created.append(doc);store[(doc.doctype,doc.name)]=doc;return doc
            doc.insert=insert;doc.save=lambda **kwargs:doc
            return doc
        f.get_doc.side_effect=get_doc
        f.db.exists.side_effect=lambda kind,name:name if (kind,name) in store else None
        f.db.get_value.side_effect=lambda *args,**kw:max([row.version for (dt,name),row in store.items() if dt=='FP Questionnaire' and name!='base'] or [0])
        with patch.dict(sys.modules,{'frappe':f}):
            first=editor.materialize(self.project,self.questions)
            self.assertEqual(first.project,'project')
            self.assertEqual(first.base_questionnaire,'base')
            count=len(created)
            self.assertEqual(editor.materialize(self.project,self.questions).name,first.name)
            self.assertEqual(len(created),count)
            first_questions=[row.label for row in created if row.doctype=='FP Question']
            self.project.scout_checks[1].label='Has maize harvesting finished?'
            second=editor.materialize(self.project,self.questions)
        self.assertNotEqual(first.name,second.name)
        self.assertEqual(second.version,first.version+1)
        self.assertEqual([row.label for row in created[:count] if row.doctype=='FP Question'],first_questions)
        self.assertEqual(store[('FP Questionnaire','base')].service_code,'land')

    def test_shared_questions_cannot_be_edited_via_service_rows(self):
        shared=Record(name='opening',question_code='S1',label='Assigned site?',validation_json='{"group":"shared","protocol_version":2}')
        self.questions.append(shared)
        self.project.scout_checks.append(Record(question='opening',label='Skip location checks',check_key='bad'))
        with self.assertRaisesRegex(ValueError,'protected'):editor.build_specs(self.project,self.questions)

if __name__=='__main__':unittest.main()
