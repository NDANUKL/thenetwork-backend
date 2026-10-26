import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from test_scout_templates import FakeSite, Record

ROOT = Path(__file__).parents[1]


def load(frappe):
    spec = importlib.util.spec_from_file_location('v2_integration_test', ROOT / 'fieldpulse/scout_v2.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'frappe':frappe}): spec.loader.exec_module(module)
    return module


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.site = FakeSite()
        self.site.conf = {}
        self.site.whitelist = lambda **kw: lambda fn: fn
        self.module = load(self.site)

    def test_default_installation_and_immutable_idempotent_catalogue(self):
        self.assertTrue(self.module.enabled())
        self.site.conf['dd_questionnaire_v2_enabled'] = False
        self.assertTrue(self.module.enabled())
        self.module.install_templates()
        self.assertEqual(len(self.site.get_all('FP Questionnaire')), 15)
        self.assertEqual(len(self.site.get_all('FP Question')), 88)
        self.module.install_templates()
        self.assertEqual(len(self.site.get_all('FP Question')), 88)
        self.site.get_doc('FP Questionnaire','DD-land-v2').schema_hash = 'changed'
        with self.assertRaisesRegex(ValueError, 'new version'): self.module.install_templates()

    def test_normal_installer_publishes_v2_and_selects_it_without_flags(self):
        spec = importlib.util.spec_from_file_location('default_templates_test', ROOT/'fieldpulse/scout_templates.py')
        templates = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.site}): spec.loader.exec_module(templates)
        templates.install_legacy_templates()
        with patch.dict(sys.modules, {'fieldpulse.scout_v2': self.module}):
            templates.install_templates()
            templates.install_templates()
            for title, name in [('Plot check', 'DD-land-v2'), ('School fees paid', 'DD-university_fees-v5')]:
                project = Record(doctype='Field Request', project_title=title)
                templates.prepare_project(project)
                self.assertEqual(project.scout_questionnaire, name)
        self.assertEqual(len(self.site.get_all('FP Questionnaire')), 30)
        self.assertEqual(len(self.site.get_all('FP Question', {'questionnaire':'DD-land-v2'})), 6)

    def test_migration_preserves_published_v2_and_visit_versions(self):
        self.site.conf['dd_questionnaire_v2_enabled'] = True
        self.site.logger = MagicMock()
        spec = importlib.util.spec_from_file_location('legacy_preservation_test', ROOT/'fieldpulse/scout_templates.py')
        legacy = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': self.site}): spec.loader.exec_module(legacy)
        for workflow, version in ((False, 2), (True, 3)):
            with self.subTest(version=version):
                self.site.conf['dd_scout_visit_workflow_enabled'] = workflow
                self.module.install_templates()
                doc = self.site.get_doc('FP Questionnaire', f'DD-land-v{version}')
                doc.schema_hash = 'published-site-hash'
                before = [dict(q) for q in self.site.get_all('FP Question', {'questionnaire':doc.name})]
                with patch.dict(sys.modules, {'fieldpulse.scout_templates':legacy}):
                    self.module.install_templates(preserve_published=True)
                self.assertEqual(doc.schema_hash, 'published-site-hash')
                self.assertEqual(before, [dict(q) for q in self.site.get_all('FP Question', {'questionnaire':doc.name})])
                with self.assertRaisesRegex(ValueError, 'new version'):self.module.install_templates()

    def test_same_site_services_share_opening_and_closing(self):
        services = self.module.catalogue()['services'][:2]
        name = self.module.install_service(services)
        questions = self.site.get_all('FP Question', {'questionnaire':name})
        self.assertEqual(len(questions),10)
        self.assertEqual(sum(q.question_code == 'S1' for q in questions),1)
        self.assertEqual(sum(q.question_code == 'S2' for q in questions),1)
        self.assertEqual(sum(q.question_code == 'S_EXTRA' for q in questions),1)
        self.assertEqual(self.module.install_service(services),name)

    def test_dispatch_requires_assigned_items_authorisation_and_confirmation_method(self):
        name = self.module.install_service([self.module.catalogue()['services'][6]])
        questions = self.site.get_all('FP Question', {'questionnaire':name})
        project = Record(scout_checks=[Record(question=q.name) for q in questions if json.loads(q.validation_json)['group']=='service'])
        with self.assertRaisesRegex(ValueError, 'checklist'): self.module.resolved_questions(project,questions)
        project.scout_checks[0].configuration_json = json.dumps(dict(items=[dict(id='period',label='Approved academic period')]))
        with self.assertRaisesRegex(ValueError, 'authorisation'): self.module.resolved_questions(project,questions)
        project.scout_authorisation = 'Adult consent and institutional office arrangements recorded'
        with self.assertRaisesRegex(ValueError, 'confirmation method'): self.module.resolved_questions(project,questions)
        project.scout_checks[1].configuration_json = json.dumps(dict(confirmation_method='Verbal'))
        pinned = self.module.resolved_questions(project,questions)
        self.assertEqual(len(pinned),5)
        project.scout_checks[0].configuration_json = '{}'
        self.assertEqual(json.loads(pinned[2]['validation_json'])['items'][0]['id'],'period')


class EvidenceLinkSecurityTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.PermissionError = PermissionError
        self.f.throw.side_effect = lambda message,*args: (_ for _ in ()).throw(ValueError(message))
        self.module = load(self.f)
        config = dict(protocol_version=2,group='service',answer_type='single',result_options=['Yes'],evidence=[dict(id='photo',kind='Photo',subject='Plot overview')])
        self.response = Record(name='response',task='task',agent='scout',status='Draft')
        self.task = Record(name='task',scout_profile='scout',status='In Progress',client_request_snapshot=json.dumps(dict(resolved_questions=[dict(name='question',question_code='1.1',validation_json=json.dumps(config))])))
        self.answer = Record(name='answer',question='question',question_code='1.1',answer_json='{"result":"Yes"}')
        self.answer.save = MagicMock()
        self.evidence = Record(name='evidence',field_task='task',scout='scout',upload_status='Uploaded',question_response='origin',evidence_type='Photo')
        self.origin = Record(task_response='response')
        self.documents = {('FP Task Response','response'):self.response,('Field Task','task'):self.task,('FP Question Response','answer'):self.answer,('FP Question Response','origin'):self.origin,('Field Evidence','evidence'):self.evidence}
        self.f.get_doc.side_effect = lambda dt,name:self.documents[(dt,name)]
        self.f.get_all.side_effect = lambda dt,**kw:[self.answer] if dt=='FP Question Response' else []
        self.f.db.exists.return_value = 'evidence'
        self.api = types.ModuleType('fieldpulse.api')
        self.api._get_scout_profile_for_user = lambda:Record(name='scout')
        self.links = [dict(attachment_id='client-file',requirement_id='1.1::photo',support_note='Plot and visible corner markers')]

    def sync(self):
        with patch.dict(sys.modules, {'fieldpulse.api':self.api}): return self.module.sync_evidence_links('response',self.links)

    def test_valid_verified_link_and_retry_are_idempotent(self):
        self.assertEqual(self.sync(),{'linked':1})
        self.assertEqual(self.sync(),{'linked':1})
        self.assertEqual(self.answer.evidence_links[0].evidence,'evidence')

    def test_cross_task_cross_response_unverified_and_wrong_media_fail_before_any_write(self):
        for key,value in [('field_task','foreign'),('scout','other'),('upload_status','Pending'),('evidence_type','Video')]:
            with self.subTest(key=key):
                original=self.evidence[key];self.evidence[key]=value
                with self.assertRaises(ValueError):self.sync()
                self.answer.save.assert_not_called();self.evidence[key]=original
        self.origin.task_response='obsolete-response'
        with self.assertRaises(ValueError):self.sync()
        self.answer.save.assert_not_called()

    def test_unknown_requirement_duplicate_and_unexplained_link_fail(self):
        for links in [[dict(self.links[0],requirement_id='not-assigned')],self.links*2,[dict(self.links[0],support_note='')]]:
            with self.subTest(links=links):
                self.links=links
                with self.assertRaises(ValueError):self.sync()
                self.answer.save.assert_not_called()

    def test_submitted_links_cannot_be_modified_but_lost_final_ack_can_retry(self):
        self.response.status='Submitted';self.task.status='Submitted'
        with self.assertRaisesRegex(ValueError,'frozen'):self.sync()
        self.f.get_all.side_effect=lambda dt,**kw:[self.answer] if dt=='FP Question Response' else [dict(evidence='evidence',requirement_id='1.1::photo',support_note=self.links[0]['support_note'])]
        self.assertEqual(self.sync(),{'linked':1})
        self.answer.save.assert_not_called()


if __name__=='__main__':unittest.main()
