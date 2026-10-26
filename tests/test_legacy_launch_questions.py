import unittest
from fieldpulse.legacy_questionnaires import answer_issue


class LegacyLaunchQuestionTests(unittest.TestCase):
    def test_zero_is_answer_and_nonfinite_or_boolean_is_not(self):
        self.assertIsNone(answer_issue('number',0))
        for value in (True,{},'NaN','Infinity',float('inf')):self.assertIsNotNone(answer_issue('number',value))
    def test_signatures_are_distinct_from_photos(self):
        self.assertIsNone(answer_issue('signature',[{'attachment_id':'sig','kind':'Signature'}]))
        self.assertIsNotNone(answer_issue('signature',[{'attachment_id':'photo','kind':'Photo'}]))
        self.assertIsNotNone(answer_issue('signature',[]))
    def test_datetime_must_have_real_date_and_offset(self):
        self.assertIsNone(answer_issue('date_time','2026-10-26T09:30+03:00'))
        for value in ('2026-02-30T09:30+03:00','yesterday','2026-10-26T09:30'):self.assertIsNotNone(answer_issue('date_time',value))
    def test_select_choices_and_optional_empty(self):
        self.assertIsNone(answer_issue('yes_no','yes'))
        self.assertIsNotNone(answer_issue('yes_no','other'))
        self.assertIsNone(answer_issue('multi_select',['a'],options=('a','b')))
        self.assertIsNotNone(answer_issue('multi_select',['old'],options=('a','b')))
        self.assertIsNone(answer_issue('text','',False))
        self.assertIsNotNone(answer_issue('text','  ',True))
    def test_gps_documents_and_unknown_types(self):
        self.assertIsNone(answer_issue('gps_point',{'latitude':0,'longitude':0}))
        self.assertIsNotNone(answer_issue('gps_point',{'latitude':True,'longitude':0}))
        self.assertIsNone(answer_issue('file_attachment',[{'attachment_id':'document'}]))
        self.assertIsNotNone(answer_issue('unknown','value'))

    def controller(self):
        import json
        import types
        from unittest.mock import MagicMock
        from tests.test_native_integration import load
        def reject(message):raise ValueError(message)
        f=types.SimpleNamespace(parse_json=json.loads,throw=reject,db=types.SimpleNamespace(exists=MagicMock(return_value=True)))
        module=load('legacy_controller_test','fieldpulse/fieldpulse/doctype/fp_task_response/fp_task_response.py',{'frappe':f,'frappe.model.document':types.SimpleNamespace(Document=object),'fieldpulse.utils':types.SimpleNamespace(haversine_distance_m=lambda *args:0)})
        controller=module.FPTaskResponse();controller.task='task'
        return controller,f
    def test_controller_checks_verified_signature_type(self):
        controller,f=self.controller()
        question={'name':'sig','label':'Sign','question_type':'signature','required':True}
        controller._require_answer(question,{'sig':{'name':'answer','answer_json':'[{"attachment_id":"sig-file","kind":"Signature"}]'}})
        self.assertEqual(f.db.exists.call_args.args[1]['evidence_type'],'Signature')
        with self.assertRaisesRegex(ValueError,'signature pad'):
            controller._require_answer(question,{'sig':{'name':'answer','answer_json':'[{"attachment_id":"photo","kind":"Photo"}]'}})
    def test_controller_compares_decoded_conditional_values(self):
        controller,_=self.controller()
        question={'display_logic_json':'{"question_code":"gate","equals":0}'}
        self.assertTrue(controller._is_question_visible(question,{'gate':{'answer_json':'0'}}))
        self.assertFalse(controller._is_question_visible(question,{'gate':{'answer_json':'"0"'}}))
