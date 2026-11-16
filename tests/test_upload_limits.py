import unittest
from unittest.mock import MagicMock
from fieldpulse.upload_policy import upload_size, validate_reservation
from test_gallery_upload import GalleryUploadTests, Row


class PolicyTests(unittest.TestCase):
    def test_size_must_be_a_positive_whole_number(self):
        for value in (0, -1, True, 1.5, '1.5', 'NaN', None, '1e9', '9' * 100):
            with self.subTest(value=value), self.assertRaises(ValueError): upload_size(value)
        self.assertEqual(upload_size('100000000'), 100_000_000)

    def test_media_and_task_limits_include_reservations(self):
        validate_reservation(100_000_000, 900_000_000)
        for size, reserved in [(100_000_001, 0), (100_000_000, 900_000_001)]:
            with self.assertRaises(ValueError): validate_reservation(size, reserved)


class UploadLimitsTests(GalleryUploadTests):
    def setUp(self):
        super().setUp()
        self.frappe.db.sql.return_value = [[0]]
        self.storage = MagicMock()
        self.module._r2_client = lambda settings: self.storage

    def test_oversized_media_never_receives_a_signed_url(self):
        with self.assertRaisesRegex(ValueError, '100 MB'):
            self.module.request_evidence_upload(**dict(self.args, file_size=100_000_001))
        self.storage.generate_presigned_url.assert_not_called()
        self.assertIsNone(self.created)

    def test_task_reservations_cannot_exceed_budget(self):
        self.frappe.db.sql.return_value = [[999_999_999]]
        with self.assertRaisesRegex(ValueError, '1 GB'):
            self.module.request_evidence_upload(**self.args)
        self.storage.generate_presigned_url.assert_not_called()
        self.assertIsNone(self.created)
        queries = [call.args[0] for call in self.frappe.db.sql.call_args_list]
        self.assertIn('FOR UPDATE', queries[0])
        self.assertIn('SUM(file_size)', queries[1])

    def test_signed_put_binds_the_reserved_content_length(self):
        self.module.request_evidence_upload(**self.args)
        parameters = self.storage.generate_presigned_url.call_args.kwargs['Params']
        self.assertEqual(parameters['ContentLength'], 123)
        self.assertEqual(parameters['ContentType'], 'image/jpeg')

    def test_existing_verified_large_media_is_not_rewritten_or_rejected(self):
        self.frappe.db.exists.side_effect = lambda dt, filters: 'SCOUT-1' if dt == 'Scout Profile' else 'OLD'
        evidence = Row(name='OLD', scout='SCOUT-1', field_task='TASK-1', question_response=None,
            task_response='RESPONSE', field_check_id='condition', upload_status='Uploaded', file_size=200_000_000)
        get_doc = self.frappe.get_doc.side_effect
        self.frappe.get_doc.side_effect = lambda dt, name=None: evidence if dt == 'Field Evidence' else get_doc(dt, name)
        self.assertEqual(self.module.request_evidence_upload(**dict(self.args, file_size=200_000_000))['upload_status'], 'Uploaded')
        self.storage.generate_presigned_url.assert_not_called()
