import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).parents[1]
class Record(dict):
    def __getattr__(self,key):return self.get(key)
    def __setattr__(self,key,value):self[key]=value


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock()
        self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.throw.side_effect=lambda message,*args:(_ for _ in ()).throw(ValueError(message))
        spec=importlib.util.spec_from_file_location('authorization_tests',ROOT/'fieldpulse/revisit_authorization.py')
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.module)
        self.doc=Record(name='revisit',source_response='source',task='task',request='request',status='Awaiting authorization',
            scope_category='Existing agreed scope',cost_arrangement='Existing agreement',contract_reference='Accepted contract clause 4',
            scout_compensation_reference='Scout agreement clause 3',authorization_notes='Reviewed the agreed terms',
            assignment_choice='Same scout',rework_questions_json='["roof"]',instructions='Photograph the roofing stage')
        self.doc.save=MagicMock()
        self.task=Record(name='task',status='Awaiting authorization',scout_profile='scout',revisit_request='revisit',save=MagicMock())
        self.source=Record(name='source',task='task',agent='scout',qa_status='Failed')
        self.profile=Record(user='scout@example.com',availability_status='Available')
        self.f.get_doc.side_effect=lambda dt,name: self.task if dt=='Field Task' else self.source if dt=='FP Task Response' else self.profile
        self.module.lock_request=lambda name:self.doc
        self.review=types.SimpleNamespace(require_reviewer=lambda:None)
        self.rework=types.SimpleNamespace(validate_assignment=MagicMock(return_value=None),create_revision=MagicMock(return_value=Record(name='revision')),create_replacement=MagicMock(return_value=Record(name='replacement')))
        self.notifications=types.SimpleNamespace(queue_rework=MagicMock())

    def act(self,action,notes=None):
        with patch.dict(sys.modules,{'fieldpulse.scout_submissions':self.review,'fieldpulse.scout_rework':self.rework,'fieldpulse.scout_notifications':self.notifications}):
            return self.module.act('revisit',action,notes)

    def test_authorization_alone_never_creates_revision_or_dispatch_notification(self):
        self.act('Authorize')
        self.assertEqual(self.doc.status,'Authorized')
        self.assertEqual(self.doc.authorized_terms_hash,self.module.terms_hash(self.doc))
        self.rework.create_revision.assert_not_called();self.rework.create_replacement.assert_not_called();self.notifications.queue_rework.assert_not_called()

    def test_pending_or_changed_terms_cannot_dispatch(self):
        with self.assertRaisesRegex(ValueError,'Authorize'):self.act('Dispatch')
        self.act('Authorize');self.doc.contract_reference='Changed contract'
        with self.assertRaisesRegex(ValueError,'terms changed'):self.act('Dispatch')
        self.notifications.queue_rework.assert_not_called()

    def test_dispatch_is_retry_safe_and_retains_same_scout_choice(self):
        self.act('Authorize');result=self.act('Dispatch')
        self.assertEqual(result['task'],'task')
        self.assertEqual(self.doc.status,'Dispatched')
        self.rework.create_revision.assert_called_once()
        self.notifications.queue_rework.assert_called_once()
        self.act('Dispatch')
        self.rework.create_revision.assert_called_once();self.notifications.queue_rework.assert_called_once()

    def test_replacement_is_created_only_after_authorization(self):
        self.doc.assignment_choice='Assign another scout';self.doc.replacement_scout='new';self.doc.reassignment_reason='Unavailable'
        self.rework.validate_assignment.return_value='new'
        self.act('Authorize');self.rework.create_replacement.assert_not_called()
        self.assertEqual(self.act('Dispatch')['task'],'replacement')
        self.rework.create_replacement.assert_called_once();self.rework.create_revision.assert_not_called()

    def test_cost_and_compensation_references_are_required_without_automatic_charges(self):
        self.doc.scout_compensation_reference=''
        with self.assertRaisesRegex(ValueError,'compensation'):self.act('Authorize')
        self.doc.scout_compensation_reference='Paid revisit terms';self.doc.cost_arrangement='Additional client charge'
        with self.assertRaisesRegex(ValueError,'client acceptance'):self.act('Authorize')
        self.doc.client_acceptance_reference='Client accepted arrangement REF-1'
        self.act('Authorize')
        self.f.enqueue.assert_not_called()
        self.rework.create_revision.assert_not_called()

    def test_additional_scope_requires_separate_approved_scope_process(self):
        self.doc.scope_category='Additional scope';self.doc.client_acceptance_reference='New scope accepted'
        with self.assertRaisesRegex(ValueError,'change-order'):self.act('Authorize')

    def test_direct_status_changes_and_authorized_terms_edits_are_rejected(self):
        previous=Record(self.doc)
        self.doc.is_new=lambda:False
        self.doc.get_doc_before_save=lambda:previous
        self.doc.status='Authorized'
        with self.assertRaisesRegex(ValueError,'authorization actions'):self.module.validate_document(self.doc)
        self.doc.status='Authorized';previous.status='Authorized'
        self.doc.contract_reference='Changed after approval'
        with self.assertRaisesRegex(ValueError,'cannot be edited'):self.module.validate_document(self.doc)

    def test_reopen_requires_a_new_authorization_and_preserves_nonactionable_hold(self):
        self.act('Decline','Cost arrangement declined')
        self.act('Reopen','Client asked us to review a new arrangement')
        self.assertEqual(self.doc.status,'Awaiting authorization')
        self.assertIsNone(self.doc.authorized_by)
        with self.assertRaisesRegex(ValueError,'Authorize'):self.act('Dispatch')
        self.act('Authorize');self.act('Return for changes','Proposed scout changed availability')
        self.assertEqual(self.doc.status,'Awaiting authorization')
        self.assertIsNone(self.doc.authorized_terms_hash)
        self.notifications.queue_rework.assert_not_called()

    def test_decline_keeps_fieldwork_nonactionable_and_requires_a_reason(self):
        with self.assertRaisesRegex(ValueError,'why'):self.act('Decline')
        self.act('Decline','Client declined the proposed arrangement')
        self.assertEqual(self.doc.status,'Declined')
        self.assertEqual(self.task.status,'Awaiting authorization')
        self.rework.create_revision.assert_not_called()

if __name__=='__main__':unittest.main()
