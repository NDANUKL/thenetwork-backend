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
