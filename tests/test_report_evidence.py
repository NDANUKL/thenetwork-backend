import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value


class ClientEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.api = MagicMock()
        self.api.whitelist = lambda **kw: lambda fn: fn
        self.api.PermissionError = PermissionError
        self.api.response = {}
        def reject(message, error=ValueError): raise error(message)
        self.api.throw.side_effect = reject
        submission = types.ModuleType('fieldpulse.scout_submissions')
        submission.require_reviewer = MagicMock()
        submission.submission_detail = MagicMock()
        spec = importlib.util.spec_from_file_location('report_media_test', ROOT / 'fieldpulse/scout_reports.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe':self.api, 'fieldpulse.scout_submissions':submission}): spec.loader.exec_module(self.module)
        self.row = Record(name='selected-row', include_client=1, evidence='evidence', caption='Permitted overview', evidence_type='Photo')
        self.report = Record(name='report', request='request', report_evidence=[self.row], review_sources_json=json.dumps([{'response':'response'}]))
        self.evidence = Record(name='evidence', field_task='task', question_response='answer', upload_status='Uploaded', evidence_type='Photo')
        self.task = Record(name='task', field_request='project', status='Approved')
        self.api.get_doc.side_effect = lambda dt, name: self.evidence if dt == 'Field Evidence' else self.task if dt == 'Field Task' else Record(name=name, task='task', agent='scout')
        self.api.db.get_value.side_effect = lambda dt,*args,**kw: 'request' if dt=='Field Request' else 'response'
        self.api.db.exists.return_value = True

    def test_bundle_contains_pdf_and_only_selected_media_with_safe_unique_paths(self):
        from io import BytesIO
        from zipfile import ZipFile
        photo = Record(original_filename='../unsafe/photo.jpg', evidence_type='Photo', file_size=3)
        video = Record(original_filename='C:\\private\\clip.mp4', evidence_type='Video', file_size=5)
        with patch.object(self.module, 'selected_evidence', return_value=[(self.row, photo), (self.row, video)]), patch.object(self.module, 'evidence_bytes', side_effect=[b'jpg', b'video']):
            data = self.module.build_evidence_bundle(self.report)
        with ZipFile(BytesIO(data)) as archive:
            self.assertEqual(archive.namelist(), ['Photos/photo-001.jpg', 'Videos/video-002.mp4'])
            self.assertEqual(archive.read('Videos/video-002.mp4'), b'video')

    def test_approved_response_without_an_existing_draft_can_open_one(self):
        response = Record(name='response', task='task', status='Submitted', qa_status='Passed', reviewed_by='coordinator', check_permission=MagicMock())
        self.task.check_permission = MagicMock()
        self.api.get_doc.side_effect = lambda dt, name: response if dt == 'FP Task Response' else self.task
        with patch.object(self.module, 'draft_for_response', return_value=None), patch.object(self.module, 'prepare_report', return_value={'report': 'new-draft'}) as create:
            self.assertEqual(self.module.open_draft_for_response('response'), {'report': 'new-draft'})
        create.assert_called_once_with('request', source_response='response')

    def test_opening_an_existing_response_report_does_not_create_a_duplicate(self):
        response = Record(name='response', task='task', status='Submitted', qa_status='Passed', reviewed_by='coordinator', check_permission=MagicMock())
        self.task.check_permission = MagicMock()
        self.report.check_permission = MagicMock()
        self.api.get_doc.side_effect = lambda dt, name: response if dt == 'FP Task Response' else self.task if dt == 'Field Task' else self.report
        with patch.object(self.module, 'draft_for_response', return_value='report'), patch.object(self.module, 'prepare_report') as create:
            self.assertEqual(self.module.open_draft_for_response('response'), {'report': 'report'})
        create.assert_not_called()

    def test_unapproved_response_cannot_create_a_draft(self):
        response = Record(task='task', status='Submitted', qa_status='Pending', check_permission=MagicMock())
        self.task.check_permission = MagicMock()
        self.api.get_doc.side_effect = lambda dt, name: response if dt == 'FP Task Response' else self.task
        with patch.object(self.module, 'prepare_report') as create:
            with self.assertRaises(ValueError): self.module.open_draft_for_response('response')
        create.assert_not_called()

    def test_evidence_archive_filenames_do_not_expose_internal_identifiers(self):
        media = Record(original_filename='TK-2026-00042-uuid.jpg', evidence_type='Photo')
        self.assertEqual(self.module.evidence_archive_name(1, media), 'Photos/photo-001.jpg')

    def test_bundle_rejects_invalid_pdf_and_oversized_media_before_download(self):
        with self.assertRaises(ValueError): self.module.build_report_bundle(self.report, b'not pdf')
        large = Record(file_size=500000001)
        with patch.object(self.module, 'selected_evidence', return_value=[(self.row, large)]), patch.object(self.module, 'evidence_bytes') as read:
            with self.assertRaises(ValueError): self.module.build_report_bundle(self.report, b'%PDF-1.7')
            read.assert_not_called()

    def test_pdf_template_has_no_images(self):
        template = (ROOT / 'fieldpulse/templates/reports/service_report.html').read_text()
        self.assertEqual(template.count('<img'), 1)
        self.assertIn('quotation_assets.logo', template)
        self.assertIn('photo_count', template)
        self.assertNotIn('doc.request', template)
        self.assertNotIn('scope.reference', template)
        self.assertNotIn('item.image', template)

    def test_only_explicitly_selected_reviewed_evidence_is_released(self):
        self.assertEqual(self.module.selected_evidence(self.report),[(self.row,self.evidence)])
        self.row.include_client = 0
        self.api.get_doc.reset_mock()
        self.assertEqual(self.module.selected_evidence(self.report),[])
        self.api.get_doc.assert_not_called()

    def test_cross_request_media_is_rejected(self):
        self.api.db.get_value.side_effect = lambda *a,**kw:'another-request'
        with self.assertRaisesRegex(ValueError,'this request'): self.module.selected_evidence(self.report)

    def test_rejected_or_unreviewed_source_response_is_not_publishable(self):
        self.api.db.exists.return_value = False
        with self.assertRaisesRegex(ValueError,'coordinator-approved'): self.module.selected_evidence(self.report)

    def test_a_report_cannot_select_media_from_a_different_submission_version(self):
        self.report.review_sources_json = '[{"response":"new-response"}]'
        with self.assertRaisesRegex(ValueError,'included in this report'): self.module.selected_evidence(self.report)

    def test_client_download_requires_ownership_before_reading_report_or_r2(self):
        payments = types.ModuleType('fieldpulse.payments')
        payments._owned = MagicMock(side_effect=PermissionError('Not owned'))
        with patch.dict(sys.modules, {'fieldpulse.payments':payments}):
            with self.assertRaises(PermissionError): self.module.download_evidence('foreign','selected-row')
        self.api.get_doc.assert_not_called()

    def test_changing_narrative_or_media_requires_regenerating_the_pdf(self):
        before = self.module.report_content_hash(self.report)
        self.row.caption = 'Corrected client-facing caption'
        self.assertNotEqual(before,self.module.report_content_hash(self.report))
        before = self.module.report_content_hash(self.report)
        self.report.findings = 'Updated findings'
        self.assertNotEqual(before,self.module.report_content_hash(self.report))


if __name__ == '__main__': unittest.main()
