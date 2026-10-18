"""Authorization, profile validation and leave/workload regressions."""
import types
import unittest
from unittest.mock import MagicMock
from test_native_integration import fake_frappe, load


class ScoutSelfServiceTests(unittest.TestCase):
    def setUp(self):
        self.f = fake_frappe()
        self.f.session.user = 'scout@example.test'
        self.f.get_roles.return_value = ['Field Agent']
        self.f.db.get_value.return_value = 1
        self.f.db.exists.return_value = 'SCT-1'
        self.f.db.count.return_value = 0
        self.profile = types.SimpleNamespace(
            name='SCT-1', user='scout@example.test', scout_name='Pauline Wanjiku',
            base_county='Nairobi', phone_number='0712345678', legacy_fp_agent=None,
            availability_status='Available', activity_status='Active', active_task_count=0,
            completed_task_count=2, flags=types.SimpleNamespace(),
            reload=MagicMock(), save=MagicMock())
        self.profile.get = lambda key: getattr(self.profile, key, None)
        self.f.get_doc.return_value = self.profile
        utils = types.ModuleType('frappe.utils')
        utils.now_datetime = lambda: '2026-10-19 12:00:00'
        self.api = load('scout_self_service_test', 'fieldpulse/scout_self_service.py', {
            'frappe': self.f, 'frappe.utils': utils,
        })

    def test_guest_disabled_and_non_scout_cannot_read_or_write(self):
        for user, enabled, roles in [('Guest', 1, []), ('disabled', 0, ['Field Agent']),
                                     ('coordinator', 1, ['Field Operations Coordinator'])]:
            self.f.session.user = user
            self.f.db.get_value.return_value = enabled
            self.f.get_roles.return_value = roles
            for method in (self.api.get_profile, self.api.update_profile):
                with self.subTest(user=user), self.assertRaises(PermissionError):
                    method()
        self.profile.save.assert_not_called()

    def test_identity_is_always_session_owned(self):
        self.api.get_profile()
        self.f.db.exists.assert_called_with('Scout Profile', {'user': 'scout@example.test'})
        with self.assertRaises(TypeError):
            self.api.update_profile(user='another@example.test')
        with self.assertRaises(TypeError):
            self.api.update_profile(activity_status='Active')

    def test_leave_with_active_tasks_preserves_assignments(self):
        self.f.db.count.return_value = 3
        result = self.api.update_profile(on_leave=True)
        self.assertEqual(result['availability_status'], 'On Leave')
        self.assertEqual(result['active_task_count'], 3)
        self.profile.save.assert_called_once_with(ignore_permissions=True)
        self.f.delete_doc.assert_not_called()

    def test_return_recalculates_from_current_workload(self):
        for count, expected in [(0, 'Available'), (2, 'Busy')]:
            self.profile.availability_status = 'On Leave'
            self.f.db.count.return_value = count
            self.assertEqual(self.api.update_profile(on_leave=False)['availability_status'], expected)

    def test_edit_details_preserves_leave_and_updates_contact(self):
        self.profile.availability_status = 'On Leave'
        user = MagicMock()
        agent = MagicMock()
        self.profile.legacy_fp_agent = 'AGT-1'
        self.f.get_doc.side_effect = [self.profile, user, agent]
        result = self.api.update_profile(full_name=' Mary  Wanjiku ', county=' Kiambu ', phone='+254 712345678')
        self.assertEqual(result['scout_name'], 'Mary Wanjiku')
        self.assertEqual(result['base_county'], 'Kiambu')
        self.assertEqual(result['availability_status'], 'On Leave')
        self.assertEqual(user.first_name, 'Mary')
        self.assertEqual(user.last_name, 'Wanjiku')
        self.assertEqual(agent.phone, '+254 712345678')

    def test_invalid_updates_do_not_save(self):
        for data in [{'full_name': 'Pauline'}, {'county': ''}, {'phone': '<script>'}, {'on_leave': 'false'}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.api.update_profile(**data)
        self.profile.save.assert_not_called()

    def test_coordinator_has_no_write_even_with_supervisor_role(self):
        self.f.get_roles.return_value = ['Field Operations Coordinator', 'Supervisor']
        self.assertFalse(self.api.profile_permission(self.profile, ptype='write', user='coordinator'))
        self.assertIsNone(self.api.profile_permission(self.profile, ptype='read', user='coordinator'))
