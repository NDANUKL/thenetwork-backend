"""Milestone capture, preference enforcement, retry safety and branded email tests."""
import json
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from tests.test_native_integration import load


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def get_doc_before_save(self): return self.get('_previous')
    def reload(self): return self


class Site:
    def __init__(self):
        self.docs = {}
        self.clock = datetime(2026,10,23,12)
        self.conf = {'dd_native_handover_approved':True}
        self.flags = types.SimpleNamespace(in_migrate=False,in_install=False)
        self.enqueue = MagicMock()
        self.db = types.SimpleNamespace(sql=MagicMock(return_value=[]), exists=lambda dt,name:(dt,name) in self.docs,
            get_value=lambda dt,name,field:'Active' if dt=='DD Recurring Plan' and field=='status' else 1, set_value=self.set_value, commit=MagicMock(), count=MagicMock(return_value=0))
        self.utils = types.SimpleNamespace(now_datetime=lambda:self.clock,today=lambda:str(self.clock.date()),get_datetime=lambda value:datetime.fromisoformat(value) if isinstance(value,str) else value)
        self.whitelist = lambda **kwargs:lambda function:function
        self.PermissionError = PermissionError
    def throw(self, message, error=ValueError): raise error(message)
    def get_roles(self): return ['System Manager']
    def add(self, doctype, name, **values):
        doc=Record(doctype=doctype,name=name,**values)
        self.docs[doctype,name]=doc
        return doc
    def get_doc(self, doctype, name=None):
        if isinstance(doctype,dict):
            doc=Record(doctype)
            def insert(**kwargs):
                doc.name=doc.event_key
                self.docs[doc.doctype,doc.name]=doc
                return doc
            doc.insert=insert
            return doc
        if name is None:name=doctype
        return self.docs[doctype,name]
    def set_value(self, doctype, name, key, value=None, **kwargs):
        self.docs[doctype,name].update(key if isinstance(key,dict) else {key:value})


class CustomerNotificationTests(unittest.TestCase):
    def setUp(self):
        self.site=Site()
        self.http=MagicMock()
        self.http.post.return_value.ok=True
        self.http.post.return_value.json.return_value={'id':'mail-1'}
        self.attempt=Record(environment='live')
        self.modules=patch.dict('sys.modules',{'frappe':self.site,'requests':self.http,
            'fieldpulse.beta_access':types.SimpleNamespace(access_status=lambda account:account.get('beta_access') or 'Approved'),
            'fieldpulse.payment_receipts':types.SimpleNamespace(verified_attempt=lambda doc:self.attempt if doc.status=='Paid' else None)})
        self.modules.start()
        self.module=load('notifications_test','fieldpulse/customer_notifications.py',{'frappe':self.site,'requests':self.http})
        self.account=self.site.add('DD Customer Account','ACCOUNT',user='client@example.com',email_verified=1,email_notifications=1,beta_access='Approved')
        self.request=self.site.add('Diaspora Request','DD-1',dd_customer_account='ACCOUNT')
        self.settings=self.site.add('DD Access Settings','DD Access Settings',customer_origin='https://example.com',resend_from_email='Desk <test@example.com>',get_password=lambda *args,**kwargs:'test-key')
    def tearDown(self): self.modules.stop()
    def source(self, kind):
        values={'details':dict(status='Details needed'), 'quotation':dict(status='Issued',version=1),
            'payment':dict(status='Paid',paid_attempt='ATT-1',kind='deposit',amount=50,currency='USD'),
            'report':dict(status='Approved',report_file='/private/files/report.pdf',report_version=1),
            'dispute':dict(status='Awaiting customer',response='Please review our response.'),
            'recurring':dict(status='Awaiting access',source_request='DD-1',plan='PLAN-1',due_date='2026-11-01',window_end='2026-11-07')}
        return self.site.add(self.module.SOURCE_TYPES[kind],kind.upper(),request='DD-1',**values[kind])
    def test_all_six_events_queue_after_commit_and_deduplicate(self):
        for kind in self.module.SOURCE_TYPES:
            source=self.source(kind)
            first=self.module.queue_event(kind,source)
            self.assertEqual(first,self.module.queue_event(kind,source))
        self.assertEqual(self.site.enqueue.call_count,6)
        self.assertTrue(all(call.kwargs['enqueue_after_commit'] for call in self.site.enqueue.call_args_list))
    def test_preferences_block_capture_and_delivery(self):
        source=self.source('details')
        self.account.email_notifications=0
        self.assertIsNone(self.module.queue_event('details',source))
        self.account.email_notifications=1
        key=self.module.queue_event('details',source)
        self.account.email_notifications=0
        self.module.send(key)
        self.assertEqual(self.site.docs[self.module.DOCTYPE,key].status,'Skipped')
        self.http.post.assert_not_called()
    def test_sender_acceptance_marks_details_sent_once(self):
        source=self.source('details');key=self.module.queue_event('details',source)
        self.module.send(key);self.module.send(key)
        self.http.post.assert_called_once()
        self.assertEqual(self.site.docs[self.module.DOCTYPE,key].status,'Sent')
        self.assertEqual(source.email_sent_at,self.site.clock)
        self.assertIn('#details-needed',self.http.post.call_args.kwargs['json']['text'])
    def test_provider_failure_retries_with_same_payload_and_key(self):
        source=self.source('quotation');key=self.module.queue_event('quotation',source)
        self.http.post.side_effect=[TimeoutError(),self.http.post.return_value]
        self.module.send(key)
        record=self.site.docs[self.module.DOCTYPE,key]
        self.assertEqual(record.status,'Pending');self.assertEqual(record.attempts,1)
        self.site.clock+=timedelta(minutes=6)
        self.module.send(key)
        calls=self.http.post.call_args_list
        self.assertEqual(calls[0].kwargs['json'],calls[1].kwargs['json'])
        self.assertEqual(calls[0].kwargs['headers']['Idempotency-Key'],calls[1].kwargs['headers']['Idempotency-Key'])
        self.assertEqual(record.status,'Sent')
    def test_expired_retry_window_requires_review(self):
        key=self.module.queue_event('quotation',self.source('quotation'))
        record=self.site.docs[self.module.DOCTYPE,key]
        record.first_attempt_at=self.site.clock-timedelta(hours=24)
        self.module.send(key)
        self.assertEqual(record.status,'Needs review');self.http.post.assert_not_called()
    def test_failed_queue_keeps_durable_pending_record(self):
        self.site.enqueue.side_effect=ConnectionError('Redis unavailable')
        key=self.module.queue_event('details',self.source('details'))
        self.assertEqual(self.site.docs[self.module.DOCTYPE,key].status,'Pending')
    def test_stale_or_already_emailed_questions_do_not_send(self):
        source=self.source('details');source.email_sent_at=self.site.clock
        self.assertIsNone(self.module.queue_event('details',source))
        source.email_sent_at=None;key=self.module.queue_event('details',source)
        source.status='Ready for review';self.module.send(key)
        self.assertEqual(self.site.docs[self.module.DOCTYPE,key].status,'Skipped')
        self.http.post.assert_not_called()
    def test_response_changes_get_distinct_events_but_repeated_saves_do_not(self):
        source=self.source('dispute');first=self.module.queue_event('dispute',source)
        source.response='A second reply';second=self.module.queue_event('dispute',source)
        self.assertNotEqual(first,second)
        self.module.send(first)
        self.assertEqual(self.site.docs[self.module.DOCTYPE,first].status,'Skipped')
    def test_message_links_and_payment_amount_are_correct(self):
        paths={'details':'#details-needed','quotation':'/dashboard/billing/DD-1','report':'#report','dispute':'/dashboard/disputes/DISPUTE','payment':'#receipts'}
        for kind,path in paths.items():
            msg=self.module.event_message(kind,self.source(kind),'DD-1','https://example.com')
            self.assertIn(path,msg['text']);self.assertNotIn('{{',msg['html'])
        self.assertIn('USD 50.00',msg['text'])
        self.attempt.environment='sandbox'
        self.assertIn('Test payment',self.module.event_message('payment',self.source('payment'),'DD-1','https://example.com')['subject'])
    def test_missing_sender_configuration_is_visible_and_retryable(self):
        self.settings.get_password=lambda *args,**kwargs:None
        key=self.module.queue_event('details',self.source('details'))
        self.module.send(key)
        record=self.site.docs[self.module.DOCTYPE,key]
        self.assertEqual(record.status,'Pending');self.assertIn('DD Access Settings',record.last_error)
        self.http.post.assert_not_called()
        status=self.module.delivery_status()
        self.assertFalse(status['configured']);self.assertFalse(status['key_configured'])
    def test_disabled_native_delivery_does_not_send_or_scan(self):
        self.site.conf['dd_native_handover_approved']=False
        self.module.send('NONEXISTENT')
        self.module.retry_pending()
        self.http.post.assert_not_called();self.site.db.sql.assert_not_called()

    def test_old_recipient_is_not_used_after_account_email_changes(self):
        key=self.module.queue_event('quotation',self.source('quotation'))
        self.http.post.side_effect=TimeoutError()
        self.module.send(key)
        self.account.user='new@example.com'
        self.site.clock+=timedelta(minutes=6)
        self.module.send(key)
        self.assertEqual(self.http.post.call_count,1)
        self.assertEqual(self.site.docs[self.module.DOCTYPE,key].status,'Skipped')

    def test_event_hooks_and_retry_schedule_are_installed(self):
        hooks=load('notification_hooks_test','fieldpulse/hooks.py',{})
        for dt in self.module.SOURCE_TYPES.values():
            self.assertEqual(hooks.doc_events[dt]['on_update'],'fieldpulse.customer_notifications.capture')
        self.assertIn('fieldpulse.customer_notifications.retry_pending',hooks.scheduler_events['cron']['*/5 * * * *'])

    def test_safe_admin_retry_keeps_original_provider_payload(self):
        key=self.module.queue_event('quotation',self.source('quotation'))
        record=self.site.docs[self.module.DOCTYPE,key]
        record.status='Needs review';record.payload='{"to":["client@example.com"]}'
        self.assertEqual(self.module.retry_notification(key)['status'],'Pending')
        self.assertEqual(record.payload,'{"to":["client@example.com"]}')
        record.status='Sent'
        count=self.site.enqueue.call_count
        self.module.retry_notification(key)
        self.assertEqual(self.site.enqueue.call_count,count)

    def test_transition_hooks_ignore_repeated_updates_and_migration(self):
        source=self.source('quotation');source._previous=Record(status='Issued')
        self.module.capture(source);self.site.enqueue.assert_not_called()
        source._previous=Record(status='Draft');self.module.capture(source)
        self.site.enqueue.assert_called_once()
        self.site.enqueue.reset_mock();self.site.flags.in_migrate=True
        self.module.capture(self.source('report'));self.site.enqueue.assert_not_called()


    def test_recurring_reminder_uses_portal_plan_link_and_suppresses_paused_plan(self):
        source=self.source('recurring')
        msg=self.module.event_message('recurring',source,'DD-1','https://example.com')
        self.assertIn('/dashboard/recurring/PLAN-1',msg['text'])
        self.assertIn('2026-11-01',msg['text'])
        key=self.module.queue_event('recurring',source)
        self.site.db.get_value=lambda dt,name,field:'Paused' if dt=='DD Recurring Plan' and field=='status' else 1
        self.module.send(key)
        self.assertEqual(self.site.docs[self.module.DOCTYPE,key].status,'Skipped')
        self.http.post.assert_not_called()
