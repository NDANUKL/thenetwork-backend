import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from tests.test_native_integration import load


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self,key,value): self[key]=value
    def get_doc_before_save(self): return self.get('_previous')
    def reload(self): return self


class ScoutAssignmentNotificationTests(unittest.TestCase):
    def setUp(self):
        self.clock=datetime(2026,10,26,12)
        self.docs={}
        self.task=Record(name='task',scout_profile='scout',status='Assigned',task_number='TASK-1',modified='2026-10-26 12:00:00')
        f=self.f=types.SimpleNamespace(flags=types.SimpleNamespace(in_migrate=False,in_install=False),session=types.SimpleNamespace(user='coordinator'),enqueue=MagicMock())
        f.utils=types.SimpleNamespace(now_datetime=lambda:self.clock,get_datetime=lambda v:datetime.fromisoformat(v) if isinstance(v,str) else v)
        f.db=types.SimpleNamespace(exists=lambda dt,key:key in self.docs,get_value=self.value,set_value=self.update,sql=MagicMock(),commit=MagicMock())
        f.get_doc=self.doc
        self.module=load('assignment_notice_tests','fieldpulse/scout_notifications.py',{'frappe':f,'requests':types.SimpleNamespace(post=MagicMock())})
    def value(self,doctype,name,field):
        if doctype=='Scout Profile':return name+'@example.test'
        if doctype=='User':return True if field=='enabled' else name
    def update(self,doctype,name,values,value=None):
        self.docs[name].update(values if isinstance(values,dict) else {values:value})
    def doc(self,doctype,name=None):
        if isinstance(doctype,dict):
            record=Record(doctype)
            def insert(**kwargs):
                if record.doctype=='DD Scout Notification':
                    record.name=record.event_key;self.docs[record.name]=record
                return record
            record.insert=insert;return record
        if doctype=='Field Task':return self.task
        return self.docs[name]
    def test_new_assignment_is_durable_and_deduplicated_when_enqueue_fails(self):
        self.f.enqueue.side_effect=RuntimeError('queue unavailable')
        self.module.capture_task(self.task)
        self.module.capture_task(self.task)
        self.assertEqual(len(self.docs),1)
        record=next(iter(self.docs.values()))
        self.assertEqual(record.event_kind,'Assignment');self.assertEqual(record.status,'Pending')
        self.assertNotIn('client',record.message.lower())
    def test_reassignment_notifies_old_and_new_scout_without_disclosing_new_details(self):
        self.task._previous=Record(scout_profile='old',status='Assigned')
        self.module.capture_task(self.task)
        records={r.event_kind:r for r in self.docs.values()}
        self.assertEqual(records['Withdrawal'].scout,'old');self.assertEqual(records['Assignment'].scout,'scout')
        self.assertTrue(self.module.delivery_current(records['Withdrawal'],self.task))
        self.assertNotIn('scout@example.test',records['Withdrawal'].message)
        self.task.scout_profile='old'
        self.assertFalse(self.module.delivery_current(records['Withdrawal'],self.task))
    def test_cancellation_and_authorization_are_captured_and_stale_assignment_skipped(self):
        self.task._previous=Record(scout_profile='scout',status='Assigned');self.task.status='Cancelled'
        self.module.capture_task(self.task)
        record=next(iter(self.docs.values()));self.assertEqual(record.event_kind,'Withdrawal');self.assertTrue(self.module.delivery_current(record,self.task))
        self.docs.clear();self.task.status='Assigned';self.task._previous=Record(scout_profile='scout',status='Awaiting authorization')
        self.module.capture_task(self.task);record=next(iter(self.docs.values()));self.assertEqual(record.event_kind,'Authorization')
        self.task.status='Cancelled';self.assertFalse(self.module.delivery_current(record,self.task))
    def test_ordinary_edits_and_migration_do_not_send_assignments(self):
        self.task._previous=Record(scout_profile='scout',status='Assigned');self.module.capture_task(self.task);self.assertEqual(self.docs,{})
        self.task._previous=None;self.f.flags.in_migrate=True;self.module.capture_task(self.task);self.assertEqual(self.docs,{})
    def test_delivery_failure_retries_same_provider_payload_and_idempotency_key(self):
        self.module.capture_task(self.task);record=next(iter(self.docs.values()))
        sender=types.SimpleNamespace(delivery_config=lambda:('test-key','sender@example.test',None))
        failed=MagicMock(ok=False);sent=MagicMock(ok=True);sent.json.return_value={'id':'provider-id'}
        with patch.dict('sys.modules',{'fieldpulse.customer_notifications':sender}),patch.object(self.module.requests,'post',side_effect=[failed,sent]) as post:
            self.module.send(record.name);self.assertEqual(record.status,'Pending');self.assertEqual(record.attempts,1)
            self.clock+=timedelta(minutes=3);self.module.send(record.name)
        self.assertEqual(record.status,'Sent');self.assertEqual(post.call_count,2)
        self.assertEqual(post.call_args_list[0].kwargs['json'],post.call_args_list[1].kwargs['json'])
        self.assertEqual(post.call_args_list[0].kwargs['headers']['Idempotency-Key'],post.call_args_list[1].kwargs['headers']['Idempotency-Key'])
