import copy
import json
import sys
import unittest
from unittest.mock import MagicMock, patch
from fieldpulse import customer_coverage as coverage


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.question = Record(name='roof-q', question_code='roof', label='Roofing stage', validation_json='{}')
        self.answer = Record(name='answer', question_code='roof', answer_json='{"result":"Observed","text":"Roof framing installed"}')
        self.check = dict(check_id='customer-1', customer_question='Has roofing started?', question_codes=['roof'])
        self.detail = dict(questions=[self.question], answers=[self.answer], evidence=[Record(name='photo',question_response='answer')], summary=[])
        self.project, self.task = Record(name='project'), Record(name='task')

    def row(self): return Record(coverage.build_check(self.check, self.detail, self.project, self.task))

    def report(self, row):
        return Record(report_checks=[row], scope_coverage_reviewed=1,
            coverage_snapshot_json=json.dumps(dict(complete=True,checks=[dict(row)])))

    def validate(self, doc):
        with patch.dict(sys.modules, {'frappe':self.f}): coverage.validate_report(doc, approving=True)

    def test_links_generate_customer_heading_findings_sources_and_evidence(self):
        row = self.row()
        self.assertEqual(row.customer_question, 'Has roofing started?')
        self.assertIn('Roof framing installed', row.findings)
        self.assertEqual(row.basis, 'Directly observed')
        self.assertEqual(row.assessment, 'Supported finding')
        self.assertEqual(json.loads(row.evidence_ids_json), ['photo'])
        self.validate(self.report(row))

    def test_missing_customer_answer_is_not_silently_omitted_or_marked_verified(self):
        self.check['question_codes'].append('cracks')
        row = self.row(); doc = self.report(row)
        self.assertEqual(row.assessment, 'Not verified')
        self.assertIn('No approved answer', row.limitations)
        with self.assertRaisesRegex(ValueError,'acknowledge'): self.validate(doc)
        row.limitation_acknowledged = 1
        self.validate(doc)
        row.assessment = 'Supported finding'
        with self.assertRaisesRegex(ValueError,'recorded gaps'): self.validate(doc)

    def test_report_cannot_drop_relabel_or_change_frozen_coverage_sources(self):
        row = self.row(); doc = self.report(row)
        doc.report_checks=[]
        with self.assertRaises(ValueError): self.validate(doc)
        doc.report_checks=[row]; row.customer_question='Different question'
        with self.assertRaisesRegex(ValueError,'frozen'): self.validate(doc)

    def test_provenance_is_not_invented_and_changes_require_an_explanation(self):
        self.answer.answer_json='{"result":"Recorded","text":"Roof framing installed"}'
        row=self.row();doc=self.report(row)
        self.assertEqual(row.basis,'Not recorded')
        row.assessment='Supported finding';row.basis='Independently checked'
        with self.assertRaisesRegex(ValueError,'Explain changes'):self.validate(doc)
        row.basis_detail='Reviewer compared the documented result with the approved reference record.'
        self.validate(doc)
        self.assertEqual(coverage.source_basis([{'source_role':'Site caretaker','text':'Roof finished'}]),'Reported by others')

    def test_legacy_mapping_must_be_confirmed_before_approval(self):
        row=self.row();doc=self.report(row);doc.coverage_snapshot_json='{"complete":false}'
        with self.assertRaisesRegex(ValueError,'questionnaire'):self.validate(doc)

    def test_dispatch_pin_takes_precedence_over_later_project_mapping(self):
        self.task.client_request_snapshot=json.dumps({'customer_coverage':{'complete':True,'reference':'accepted-quote','checks':[self.check]}})
        self.project.customer_checks=[]
        mapped=coverage.task_mapping(self.task,self.project)
        self.assertEqual(mapped['reference'],'accepted-quote')
        self.assertFalse(mapped['retrospective'])

    def test_required_evidence_errors_force_an_explicit_unverified_finding(self):
        self.detail['summary']=[dict(code='roof',errors=['Required roof photo missing'],reasons=[])]
        row=self.row()
        self.assertEqual(row.assessment,'Not verified')
        self.assertIn('Required roof photo missing',row.limitations)

    def test_legacy_required_media_is_checked_even_without_v2_summary(self):
        self.question.validation_json='{"mandatory_evidence":true}'
        self.detail['evidence']=[Record(name='photo',question_response='answer',evidence_type='Photo')]
        self.assertIn('Required video missing',coverage.required_review_errors(self.detail)[0])
        self.assertEqual(self.row().assessment,'Not verified')

    def test_project_confirmation_validates_accepted_scope_and_stamps_the_reviewer(self):
        project=Record(name='project',scout_questionnaire='library',scout_checks=[Record(question='roof-q')],scout_checks_confirmed=1,
            customer_checks=[Record(check_id='check-1',customer_question='Has roofing started?',question_codes='roof')],
            customer_checks_confirmed=1,customer_scope_reference='quote',diaspora_request='request',is_new=lambda:False,get_doc_before_save=lambda:None)
        quote=Record(request='request',status='Accepted',version=2)
        self.f.get_all.return_value=[self.question]
        self.f.get_doc.return_value=quote
        self.f.session.user='reviewer'
        import types
        with patch.dict(sys.modules,{'frappe':self.f,'fieldpulse.scout_submissions':types.SimpleNamespace(require_reviewer=lambda:None)}):
            coverage.validate_project(project)
            self.assertEqual(project.customer_scope_version,'2')
            self.assertEqual(project.customer_checks_reviewed_by,'reviewer')
            self.assertEqual(project.customer_checks[0].linked_checks,'Roofing stage')
            quote.status='Issued'
            with self.assertRaisesRegex(ValueError,'accepted quotation'):coverage.validate_project(project)

    def test_changed_mapping_invalidates_confirmation_instead_of_silently_reusing_it(self):
        old=Record(customer_checks_confirmed=1,customer_scope_reference='quote',customer_checks=[Record(check_id='c',customer_question='Old question',question_codes='roof')])
        project=Record(scout_questionnaire='library',scout_checks=[Record(question='roof-q')],scout_checks_confirmed=1,
            customer_checks_confirmed=1,customer_scope_reference='quote',customer_checks=[Record(check_id='c',customer_question='New question',question_codes='roof')],
            is_new=lambda:False,get_doc_before_save=lambda:old)
        self.f.get_all.return_value=[self.question]
        with patch.dict(sys.modules,{'frappe':self.f}):coverage.validate_project(project)
        self.assertEqual(project.customer_checks_confirmed,0)
        self.f.get_doc.assert_not_called()


if __name__=='__main__':unittest.main()
