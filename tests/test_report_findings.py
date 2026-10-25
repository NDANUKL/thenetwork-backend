import unittest
from fieldpulse.report_findings import finding_text


class FindingTests(unittest.TestCase):
    def test_structured_values_are_labeled_and_evidence_exceptions_are_retained(self):
        question = {'validation_json': {'items': [{'id': 'wall', 'label': 'Boundary wall'}]}}
        answer = dict(result='Observed', text='Northern boundary', source_role='Site caretaker',
            items={'wall': {'result': 'Damaged', 'quantity': 0, 'condition': 'Cracked', 'explanation_ref': 'S3'}},
            exceptions={'1.1::photo': {'reason': 'Permission refused', 'detail': 'No indoor recording'}},
            media=[{'local_uri': 'private-device-path'}])
        text, limitations = finding_text(question, answer, {'S3': {'text': 'Access restricted'}})
        for value in ('Boundary wall', 'Damaged', 'Quantity: 0', 'Cracked', 'Access restricted', 'Site caretaker'):
            self.assertIn(value, text)
        self.assertIn('Permission refused', limitations[0])
        self.assertNotIn('1.1::photo', limitations[0])
        self.assertNotIn('private-device-path', text)

    def test_blocked_checks_do_not_publish_stale_item_findings(self):
        text, _ = finding_text({}, {'blocked': True, 'text': 'No access', 'items': {'old': {'text': 'Outdated observation'}}}, {})
        self.assertIn('Unable to check', text)
        self.assertNotIn('Outdated observation', text)

    def test_legacy_text_and_boolean_answers_are_not_dropped(self):
        self.assertEqual(finding_text({}, '"Gate locked"', {})[0], 'Gate locked')
        self.assertEqual(finding_text({}, 'true', {})[0], 'Yes')
        self.assertEqual(finding_text({}, {}, {}, 'Written answer')[0], 'Written answer')


if __name__ == '__main__': unittest.main()
