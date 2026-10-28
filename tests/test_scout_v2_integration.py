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

    def test_historical_evidence_links_have_no_mutation_endpoint(self):
        self.assertFalse(hasattr(self.module,'sync_evidence_links'))
        self.f.db.set_value.assert_not_called()

if __name__=='__main__':unittest.main()
