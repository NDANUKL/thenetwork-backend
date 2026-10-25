"""Exercise the actual action boundary with a small fake Frappe site."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).parents[1]

class Record(dict):
    def __getattr__(self,key):return self.get(key)
    def __setattr__(self,key,value):self[key]=value

class FinanceControlsTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock()
        self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.throw.side_effect=lambda message,error=ValueError:(_ for _ in ()).throw(error(message))
        self.f.session.user='finance@example.com'
        self.f.conf={'dd_finance_enabled':1}
        self.f.flags=types.SimpleNamespace()
        self.f.PermissionError=PermissionError
        self.f.get_roles.return_value=['Finance']
        modules={'frappe':self.f,'frappe.model.document':types.SimpleNamespace(Document=object)}
        def load(name,path,extra=None):
            spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules,{**modules,**(extra or {})}):spec.loader.exec_module(module)
            return module
        self.documents=load('finance_documents_test','fieldpulse/finance_documents.py')
        self.finance=load('finance_test','fieldpulse/finance.py',{'fieldpulse.finance_documents':self.documents})
        self.actions=load('finance_actions_test','fieldpulse/finance_actions.py',{'fieldpulse.finance_documents':self.documents,'fieldpulse.finance':self.finance})
        self.real_lock_context=self.actions.lock_context
        self.actions.lock_context=MagicMock()
        self.actions.save_action=MagicMock()
        self.actions.audit=MagicMock()
        self.actions.private_proof=MagicMock()
        self.actions.notify=MagicMock()
        self.doc=Record(doctype='DD Scout Payout',name='PAY-1',status='Processing',scout='scout',beneficiary='recipient',currency='KES',total='1000',allocations=[],check_permission=MagicMock())
        self.f.get_doc.return_value=self.doc

    def act(self,action,data=None):return self.actions.act(self.doc.doctype,self.doc.name,action,data or {})

    def test_non_finance_cannot_release_money(self):
        self.f.get_roles.return_value=['Field Operations Coordinator']
        with self.assertRaises(PermissionError):self.act('Confirm paid')
        self.actions.save_action.assert_not_called()

    def test_feature_default_off(self):
        self.f.conf={}
        with self.assertRaisesRegex(ValueError,'not enabled'):self.act('Begin processing')

    def test_uncertain_transfer_cannot_be_cancelled_or_failed(self):
        with self.assertRaisesRegex(ValueError,'uncertain'):self.act('Cancel before execution',{'notes':'Timeout'})
        with self.assertRaisesRegex(ValueError,'uncertain'):self.act('Confirm failed',{'notes':'Timeout','evidence':'/private/files/proof.pdf'})
        self.actions.save_action.assert_not_called()

    def test_wrong_recipient_or_amount_does_not_settle_correct_scout(self):
        for data in ({'recipient_matches':False,'actual_amount':'1000'},{'recipient_matches':True,'actual_amount':'900'}):
            with self.assertRaisesRegex(ValueError,'actual amount'):self.act('Confirm paid',dict(notes='Checked',evidence='/private/files/proof.pdf',reference='REF',**data))
        self.actions.save_action.assert_not_called()

    def test_work_approver_needs_independent_review_of_current_economics(self):
        self.doc.independent_reviewer='other@example.com';self.doc.independent_review_notes='Checked';self.doc.independent_review_hash=self.documents.review_hash(self.doc)
        with patch.dict(sys.modules,{'fieldpulse.finance_documents':self.documents}):
            self.finance.independent(self.doc,['finance@example.com'])
            self.doc.beneficiary='changed-recipient'
            with self.assertRaisesRegex(ValueError,'independently review'):self.finance.independent(self.doc,['finance@example.com'])

    def test_only_identical_paid_retry_is_idempotent(self):
        self.doc.status='Paid';self.doc.reference='REF1'
        self.assertEqual(self.act('Confirm paid',{'reference':'REF1','actual_amount':'1000'})['status'],'Paid')
        with self.assertRaisesRegex(ValueError,'different confirmed'):self.act('Confirm paid',{'reference':'REF2','actual_amount':'1000'})
        self.actions.save_action.assert_not_called()

    def test_client_flags_do_not_authorise_history_mutation(self):
        self.f.flags.dd_finance_action=True
        self.assertFalse(self.documents.internal(self.doc))
        with self.documents.action_document(self.doc):self.assertTrue(self.documents.internal(self.doc))
        self.assertFalse(self.documents.internal(self.doc))

    def test_changed_lock_scope_requires_fresh_review(self):
        self.doc.reload=lambda:setattr(self.doc,'beneficiary','new-recipient')
        with self.assertRaisesRegex(ValueError,'details changed'):self.real_lock_context(self.doc)

    def test_pending_recipient_cannot_be_edited_to_another_account(self):
        previous=Record(status='Pending verification',scout='scout',method='M-Pesa',account_holder='Scout',institution='Operator',account_number='********')
        doc=Record(previous,doctype='DD Payout Beneficiary',method='Bank',meta=Record(fields=[]),is_new=lambda:False,get_doc_before_save=lambda:previous)
        with self.assertRaisesRegex(ValueError,'new re-authenticated'):self.documents.validate(doc)

    def test_direct_child_mutation_is_not_a_payment_edit_route(self):
        self.assertFalse(self.documents.child_permission(Record(),ptype='write'))
        self.assertFalse(self.documents.child_permission(Record(),ptype='delete'))

    def test_refund_acknowledgement_stays_pending(self):
        self.doc=Record(doctype='DD Customer Refund',name='REFUND-1',status='Approved',payment='payment',check_permission=MagicMock())
        self.f.get_doc.return_value=self.doc
        result=self.act('Record provider pending',{'notes':'Provider received request','reference':'PROVIDER-CASE'})
        self.assertEqual(result['status'],'Provider pending')
        self.assertNotIn('confirmed_at',self.doc)

    def test_refund_cannot_be_confirmed_without_actual_reconciliation(self):
        self.doc=Record(doctype='DD Customer Refund',name='REFUND-1',status='Provider pending',payment='payment',amount='1000',check_permission=MagicMock())
        self.f.get_doc.return_value=self.doc
        with self.assertRaisesRegex(ValueError,'Reconcile'):self.act('Confirm refund',{'notes':'Acknowledged','evidence':'/private/files/proof.pdf','actual_amount':'1000'})

    def test_no_cash_movement_is_queued_by_action(self):
        self.act('Hold',{'notes':'Awaiting bank confirmation'})
        self.assertEqual(self.doc.status,'On hold')
        self.f.enqueue.assert_not_called()
        self.f.db.commit.assert_not_called()


if __name__=='__main__':unittest.main()
