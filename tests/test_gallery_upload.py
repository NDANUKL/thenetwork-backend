import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

class Row(dict):
    def __getattr__(self, key): return self.get(key)
    def insert(self, **kwargs): self['name'] = 'EVIDENCE'

class GalleryUploadTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).parents[1]
        fixture = json.loads((root/'tests/fixtures/task-brief-v1.json').read_text())
        self.frappe = MagicMock()
        self.frappe.whitelist.return_value = lambda fn: fn
        self.frappe.throw.side_effect = lambda message, *args: (_ for _ in ()).throw(ValueError(message))
        self.frappe.db.exists.side_effect = lambda doctype, filters: 'SCOUT-1' if doctype == 'Scout Profile' else None
        self.frappe.db.get_value.side_effect = lambda dt, name, field: 'SCOUT-1' if field == 'scout_profile' else 'In Progress'
        self.task = Row(task_brief_version='BRIEF')
        self.response = Row(task='TASK-1', agent='SCOUT-1', status='Draft', arrival_check_json=json.dumps(fixture['submission']['arrival']))
        self.created = None
        def get_doc(doctype, name=None):
            if isinstance(doctype, dict):
                self.created = Row(doctype)
                return self.created
            return self.task if doctype == 'Field Task' else self.response
        self.frappe.get_doc.side_effect = get_doc
        workflow = types.SimpleNamespace(snapshot=lambda task: dict(site=fixture['site'], check_ids=['condition']), decoded=lambda value, default: json.loads(value))
        utils = types.SimpleNamespace(now_datetime=lambda: datetime(2026,10,31))
        mobile = types.SimpleNamespace(mobile_datetime=lambda value: None if value is None else datetime(2026,10,30))
        modules = {'frappe': self.frappe, 'frappe.utils': utils, 'boto3': MagicMock(), 'botocore.client': MagicMock(), 'fieldpulse.mobile_datetime': mobile, 'fieldpulse.task_brief_workflow': workflow}
        self.patch = patch.dict(sys.modules, modules);self.patch.start();self.addCleanup(self.patch.stop)
        spec = importlib.util.spec_from_file_location('gallery_evidence_test',root/'fieldpulse/evidence.py')
        self.module = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.module._r2_settings = lambda: {'bucket':'test'}
        self.module._r2_client = lambda settings: MagicMock()
        self.args = dict(field_task='TASK-1', client_uuid='FILE', filename='photo.jpg', mime_type='image/jpeg', file_size=123, evidence_type='Photo', metadata_origin='Gallery', task_response='RESPONSE', field_check_id='condition')

    def test_gallery_cannot_claim_current_time_or_gps(self):
        self.module.request_evidence_upload(**self.args, captured_at='2026-10-30T10:00:00Z', gps_lat=1, gps_lng=2, accuracy_m=1, location_sampled_at='2026-10-30T10:00:00Z')
        self.assertEqual(self.created['metadata_origin'],'Gallery')
        self.assertEqual(self.created['clarification_required'],1)
        for key in ('captured_at','gps_lat','gps_lng','accuracy_m','location_sampled_at'):
            self.assertIsNone(self.created[key])

    def test_gallery_video_is_accepted_for_review_but_unverified_arrival_remains_blocked(self):
        self.module.request_evidence_upload(**dict(self.args,filename='clip.mp4',evidence_type='Video',mime_type='video/mp4',captured_at='2026-10-30T10:00:00Z',gps_lat=1,gps_lng=2,accuracy_m=1,location_sampled_at='2026-10-30T10:00:00Z'))
        self.assertEqual(self.created['metadata_origin'],'Gallery')
        self.assertEqual(self.created['clarification_required'],1)
        for key in ('captured_at','gps_lat','gps_lng','accuracy_m','location_sampled_at'):
            self.assertIsNone(self.created[key])
        self.response['arrival_check_json']='{}'
        with self.assertRaisesRegex(ValueError,'Verify arrival'):
            self.module.request_evidence_upload(**dict(self.args,filename='clip.mp4',evidence_type='Video',mime_type='video/mp4'))

    def test_camera_still_requires_original_capture_timestamp(self):
        with self.assertRaisesRegex(ValueError,'timestamp'):
            self.module.request_evidence_upload(**dict(self.args,metadata_origin='Camera'))
