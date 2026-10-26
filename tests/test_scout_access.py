"""Admission decisions, privilege boundaries and revocation regressions."""
import types
import unittest
from unittest.mock import MagicMock, patch
from test_native_integration import fake_frappe, load


def record(**values):
    doc = MagicMock()
    for key, value in values.items():
        setattr(doc, key, value)
    doc.get.side_effect = lambda key: getattr(doc, key, None)
    return doc


class ScoutAccessTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_frappe()
        self.f.session.user = 'coordinator@example.test'
        self.f.get_roles.return_value = ['Field Operations Coordinator']
        self.f.flags = types.SimpleNamespace(dd_scout_admission_write=False, in_migrate=False)
        self.f.db.get_value.return_value = None
        self.f.db.exists.return_value = None
        self.api = load('scout_access_test', 'fieldpulse/scout_access.py', {
            'frappe': self.f, 'frappe.utils': types.SimpleNamespace(now_datetime=lambda: 'now'),
        })
        self.app = record(name='SAPP-1', user='scout@example.test', email='scout@example.test',
                          full_name='Pauline Wanjiku', county='Kiambu', phone='0712345678',
                          status='Pending', scout_profile=None)

    def test_only_reviewers_can_approve_reject_or_deactivate(self):
        for roles in ([], ['Field Agent'], ['Supervisor'], ['Finance']):
            self.f.get_roles.return_value = roles
            for action in (lambda: self.api.review_application('SAPP-1', 'Approved'),
                           lambda: self.api.review_application('SAPP-1', 'Rejected', 'Reason'),
                           lambda: self.api.deactivate_scout('SCT-1', 'Reason'),
                           lambda: self.api.reactivate_scout('SCT-1', 'Reason')):
                with self.subTest(roles=roles), self.assertRaises(PermissionError):
                    action()
        self.f.get_doc.assert_not_called()

    def test_approval_creates_agent_profile_and_enables_user(self):
        user, agent, profile = record(enabled=0), record(name='AGT-1'), record(name='SCT-1')
        self.f.get_doc.side_effect = [self.app, user, agent, profile]
        result = self.api.review_application('SAPP-1', 'Approved')
        self.assertEqual(result, {'status': 'Approved', 'scout_profile': 'SCT-1'})
        self.assertEqual(user.enabled, 1)
        user.append_roles.assert_called_once_with('Field Agent')
        self.assertEqual(agent.status, 'Active')
        self.assertEqual(profile.scout_name, 'Pauline Wanjiku')
        self.assertEqual(profile.base_county, 'Kiambu')
        self.assertEqual(profile.phone_number, '0712345678')
        self.assertEqual(self.app.reviewed_by, 'coordinator@example.test')
        self.assertFalse(self.f.flags.dd_scout_admission_write)
        self.f.db.commit.assert_not_called()

    def test_rejection_keeps_applicant_disabled_and_creates_no_scout(self):
        self.f.get_doc.return_value = self.app
        result = self.api.review_application('SAPP-1', 'Rejected', 'Not eligible')
        self.assertEqual(result['status'], 'Rejected')
        self.assertEqual(self.app.review_reason, 'Not eligible')
        self.f.get_doc.assert_called_once_with('Scout Application', 'SAPP-1', for_update=True)

    def test_review_is_serialized_and_cannot_repeat_or_reverse_decisions(self):
        self.f.get_doc.return_value = self.app
        for status in ('Approved', 'Rejected', 'Deactivated'):
            self.app.status = status
            with self.assertRaises(ValueError):
                self.api.review_application('SAPP-1', 'Approved')
        self.assertTrue(self.f.get_doc.call_args.kwargs['for_update'])
        self.app.save.assert_not_called()

    def test_invalid_decisions_and_missing_reasons_fail_before_writes(self):
        for action in (lambda: self.api.review_application('SAPP-1', 'Active'),
                       lambda: self.api.review_application('SAPP-1', 'Rejected', ' '),
                       lambda: self.api.deactivate_scout('SCT-1', ' ')):
            with self.assertRaises(ValueError): action()
        self.f.get_doc.assert_not_called()

    def test_pending_rejected_deactivated_block_password_and_existing_sessions(self):
        for status in ('Pending', 'Rejected', 'Deactivated'):
            self.f.db.get_value.side_effect = lambda dt, *args: status if dt == 'Scout Application' else 1
            for action in (lambda: self.api.on_login(types.SimpleNamespace(user=self.app.user)), self.api.validate_auth):
                with self.subTest(status=status), self.assertRaises(PermissionError): action()

    def test_existing_scouts_need_no_reapplication_but_disabled_accounts_are_blocked(self):
        self.f.db.get_value.side_effect = lambda dt, *args: 1 if dt == 'User' else None
        self.api.check_access(self.app.user)
        self.f.db.get_value.side_effect = lambda dt, *args: 0 if dt == 'User' else None
        with self.assertRaises(PermissionError): self.api.check_access(self.app.user)
        self.f.db.get_value.side_effect = lambda dt, *args: 'Deactivated' if dt == 'Scout Profile' else 1
        with self.assertRaises(PermissionError): self.api.check_access(self.app.user)

    def test_document_edits_cannot_self_approve_or_reenable(self):
        with self.assertRaises(PermissionError): self.api.validate_application(self.app)
        user = record(name=self.app.user, enabled=1, roles=[])
        self.f.db.get_value.return_value = 'Rejected'
        with self.assertRaises(ValueError): self.api.validate_user(user)
        self.f.db.get_value.return_value = 'Pending'
        user.enabled = 0
        user.get.side_effect = lambda key: [types.SimpleNamespace(role='Field Agent')] if key == 'roles' else None
        with self.assertRaises(ValueError): self.api.validate_user(user)

    def test_new_profiles_require_approval_and_access_fields_cannot_be_edited(self):
        profile = record(user=self.app.user, access_status='Active')
        profile.is_new.return_value = True
        with self.assertRaises(ValueError): self.api.validate_profile(profile)
        self.f.db.get_value.return_value = 'Approved'
        self.api.validate_profile(profile)
        profile.is_new.return_value = False
        previous = record(user=self.app.user, access_status='Deactivated')
        profile.get_doc_before_save.return_value = previous
        with self.assertRaises(ValueError): self.api.validate_profile(profile)

    def test_deactivation_retains_records_suspends_agent_and_revokes_sessions_after_commit(self):
        profile = record(name='SCT-1', user=self.app.user, access_status='Active')
        user = record(name=self.app.user, enabled=1, api_key='old', api_secret='old')
        self.f.get_doc.side_effect = [profile, user]
        self.f.get_all.return_value = ['AGT-1']
        clear = MagicMock()
        with patch.dict('sys.modules', {'frappe.sessions': types.SimpleNamespace(clear_sessions=clear)}):
            self.assertEqual(self.api.deactivate_scout('SCT-1', 'Left the team'), {'status': 'Deactivated'})
        self.assertEqual(profile.access_status, 'Deactivated')
        self.assertEqual(profile.deactivation_reason, 'Left the team')
        self.assertEqual(user.enabled, 0)
        self.assertIsNone(user.api_key)
        self.assertIsNone(user.api_secret)
        self.f.db.set_value.assert_called_with('FP Agent', 'AGT-1', 'status', 'Suspended')
        clear.assert_not_called()
        self.f.db.after_commit.add.call_args.args[0]()
        clear.assert_called_once_with(user=self.app.user, force=True)
        self.f.delete_doc.assert_not_called()
        self.f.db.commit.assert_not_called()

    def test_identity_records_cannot_be_deleted_to_bypass_block(self):
        with self.assertRaises(ValueError): self.api.prevent_application_deletion(self.app)
        self.f.db.exists.return_value = 'SAPP-1'
        with self.assertRaises(ValueError): self.api.protect_identity(record(name=self.app.user))

    def test_failed_approval_leaves_commit_to_transaction_and_resets_internal_flag(self):
        user = record(enabled=0)
        user.save.side_effect = RuntimeError('write failed')
        self.f.get_doc.side_effect = [self.app, user]
        with self.assertRaises(RuntimeError): self.api.review_application('SAPP-1', 'Approved')
        self.assertFalse(self.f.flags.dd_scout_admission_write)
        self.f.db.commit.assert_not_called()

    def test_reactivation_restores_same_approved_profile_and_preserves_leave_and_audit(self):
        profile = record(name='SCT-1', user=self.app.user, access_status='Deactivated',
                         availability_status='On Leave', deactivation_reason='Left the team')
        user = record(name=self.app.user, enabled=0, roles=[types.SimpleNamespace(role='Field Agent')],
                      api_key=None, api_secret=None)
        self.app.status, self.app.scout_profile = 'Deactivated', 'SCT-1'
        self.f.db.exists.return_value = 'SAPP-1'
        self.f.get_doc.side_effect = [profile, self.app, user]
        self.f.get_all.return_value = ['AGT-1']
        self.assertEqual(self.api.reactivate_scout('SCT-1', 'Returned to the team'), {'status': 'Active'})
        self.assertEqual(profile.access_status, 'Active')
        self.assertEqual(profile.reactivated_by, 'coordinator@example.test')
        self.assertEqual(profile.reactivation_reason, 'Returned to the team')
        self.assertEqual(profile.deactivation_reason, 'Left the team')
        self.assertEqual(profile.availability_status, 'On Leave')
        self.assertEqual(self.app.status, 'Approved')
        self.assertEqual(user.enabled, 1)
        self.assertIsNone(user.api_key)
        self.assertIsNone(user.api_secret)
        user.append_roles.assert_not_called()
        self.f.db.set_value.assert_called_once_with('FP Agent', 'AGT-1', 'status', 'Active')
        self.f.db.after_commit.add.assert_not_called()
        self.f.db.commit.assert_not_called()

    def test_deactivation_cannot_be_used_for_pending_rejected_or_mismatched_applications(self):
        profile = record(name='SCT-1', user=self.app.user, access_status='Active')
        self.f.db.exists.return_value = 'SAPP-1'
        for status, link in [('Pending', 'SCT-1'), ('Rejected', 'SCT-1'), ('Approved', 'SCT-other')]:
            self.app.status, self.app.scout_profile = status, link
            self.f.get_doc.side_effect = [profile, self.app]
            with self.subTest(status=status, link=link), self.assertRaisesRegex(ValueError, 'Only approved'):
                self.api.deactivate_scout('SCT-1', 'Reason')
        profile.save.assert_not_called()

    def test_legacy_scout_can_be_reactivated_without_creating_an_application(self):
        profile = record(name='SCT-old', user=self.app.user, access_status='Deactivated')
        user = record(roles=[types.SimpleNamespace(role='Field Agent')])
        self.f.get_doc.side_effect = [profile, user]
        self.api.reactivate_scout('SCT-old', 'Returned')
        self.assertEqual(user.enabled, 1)
        self.assertEqual(self.f.get_doc.call_count, 2)

    def test_reactivation_cannot_approve_pending_rejected_or_unlinked_applications(self):
        profile = record(name='SCT-1', user=self.app.user, access_status='Deactivated')
        self.f.db.exists.return_value = 'SAPP-1'
        for status, link in [('Pending', 'SCT-1'), ('Rejected', 'SCT-1'), ('Approved', 'SCT-other')]:
            self.app.status, self.app.scout_profile = status, link
            self.f.get_doc.side_effect = [profile, self.app]
            with self.subTest(status=status, link=link), self.assertRaisesRegex(ValueError, 'approval'):
                self.api.reactivate_scout('SCT-1', 'Return')
        profile.save.assert_not_called()

    def test_reactivation_requires_reason_inactive_profile_and_existing_scout_role(self):
        with self.assertRaises(ValueError): self.api.reactivate_scout('SCT-1', '')
        profile = record(name='SCT-1', user=self.app.user, access_status='Active')
        self.f.get_doc.return_value = profile
        with self.assertRaises(ValueError): self.api.reactivate_scout('SCT-1', 'Return')
        profile.access_status = 'Deactivated'
        user = record(roles=[])
        self.f.get_doc.side_effect = [profile, user]
        with self.assertRaisesRegex(ValueError, 'Field Agent role'):
            self.api.reactivate_scout('SCT-1', 'Return')
        profile.save.assert_not_called()

    def test_deactivated_scout_cannot_receive_a_new_assignment(self):
        module = load('scout_access_task_test', 'fieldpulse/fieldpulse/doctype/field_task/field_task.py', {
            'frappe': self.f,
            'frappe.model.document': types.SimpleNamespace(Document=object),
            'frappe.utils': types.SimpleNamespace(now_datetime=lambda: 'now'),
            'fieldpulse.fieldpulse.doctype.scout_profile.scout_profile': types.SimpleNamespace(
                recalculate_workload_and_availability=MagicMock()),
        })
        task = record(scout_profile='SCT-1')
        task.is_new.return_value = True
        self.f.db.get_value.return_value = 'Deactivated'
        with self.assertRaisesRegex(ValueError, 'deactivated'):
            module.FieldTask._validate_scout_assignment(task, None)
        self.f.db.get_value.assert_called_with('Scout Profile', 'SCT-1', 'access_status', for_update=True)


if __name__ == '__main__':
    unittest.main()
