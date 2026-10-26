import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock,patch
from tests.test_native_integration import load


class ScoutInboxTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock();self.f.session.user='scout@example.test';self.f.db.exists.return_value=True
        self.f.PermissionError=PermissionError
        def reject(message,error=ValueError):raise error(message)
        self.f.throw.side_effect=reject
        self.module=load('scout_inbox_test','fieldpulse/scout_inbox.py',{'frappe':self.f})
    def payload(self):
        with patch.dict('sys.modules',{'frappe.utils':types.SimpleNamespace(get_system_timezone=lambda:'Africa/Nairobi')}):return self.module.notification_payload()
    def test_inbox_is_recipient_scoped_and_includes_finance_account_and_generic_alerts(self):
        self.f.get_all.return_value=[dict(name=str(i),subject='<b>'+kind+'</b>',email_content='<p>Details</p><script>hidden secret</script>',creation=datetime(2026,10,26,9),read=0,document_type=doctype,document_name='reference') for i,(kind,doctype) in enumerate([('Payment recorded','DD Scout Payout'),('Expense approved','DD Scout Expense'),('Privacy updated','Scout Data Request'),('Account updated','Scout Profile'),('General notice','Other')])]
        rows=self.payload()
        self.assertEqual([row['target_type'] for row in rows],['earnings','earnings','privacy','profile','none'])
        self.assertTrue(all(row['body']=='Details' for row in rows))
        self.assertTrue(all(row['created_at'].endswith('+03:00') for row in rows))
        self.assertEqual(self.f.get_all.call_args.kwargs['filters'],{'for_user':'scout@example.test'})
        self.assertEqual(self.f.get_all.call_args.kwargs['limit_page_length'],100)
    def test_guest_and_non_scout_cannot_read_other_notifications(self):
        self.f.session.user='Guest'
        with self.assertRaises(PermissionError):self.payload()
        self.f.get_all.assert_not_called()
        self.f.session.user='other@example.test';self.f.db.exists.return_value=False
        with self.assertRaises(PermissionError):self.payload()
        self.f.get_all.assert_not_called()
    def test_task_event_normalization_and_body_bounds(self):
        self.f.get_all.return_value=[dict(name='task-alert',subject='Rework required: Correct answers',email_content='x'*3000,creation=datetime(2026,10,26,9),read=1,document_type='Field Task',document_name='task')]
        row=self.payload()[0]
        self.assertEqual(row['event_kind'],'Review feedback updated');self.assertEqual(row['target_type'],'task');self.assertEqual(len(row['body']),2000);self.assertTrue(row['read'])
