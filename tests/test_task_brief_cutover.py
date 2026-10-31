import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock()
        self.f.throw.side_effect=lambda msg:(_ for _ in ()).throw(ValueError(msg))
        spec=importlib.util.spec_from_file_location('cutover_tests',Path(__file__).parents[1]/'fieldpulse/task_brief_cutover.py')
        self.m=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.m)
        self.f.local.site='other.example'

    def test_open_legacy_work_blocks_rollout_without_mutation(self):
        self.f.get_all.return_value=[type('Task',(),{'name':'OPEN'})()]
        with self.assertRaisesRegex(ValueError,'cutover blocked'):self.m.assert_ready()
        self.f.db.set_value.assert_not_called()
        self.assertFalse(self.m.inventory()['device_work_verified'])

    def test_finished_cutover_and_fresh_install_can_migrate(self):
        self.f.get_all.return_value=[]
        self.m.assert_ready()
        self.assertTrue(self.m.inventory()['ready'])
        self.f.db.exists.return_value=False
        self.f.get_all.reset_mock();self.m.assert_ready();self.f.get_all.assert_not_called()

    def test_inventory_scopes_scout_and_excludes_terminal_tasks(self):
        self.m.open_legacy_tasks('SCOUT')
        filters=self.f.get_all.call_args.kwargs['filters']
        self.assertEqual(filters['scout_profile'],'SCOUT')
        self.assertEqual(filters['task_brief_version'],['is','not set'])
        self.assertEqual(filters['status'],['not in',['Approved','Cancelled','Rejected']])

    def authorized_site(self, statuses=('Assigned', 'Submitted')):
        self.f.local.site=self.m.AUTHORIZED_SITE
        self.rows=[SimpleNamespace(name=name,status=status,field_request='PROJECT',scout_profile='SCOUT',task_brief_version=None)
            for name,status in zip(self.m.AUTHORIZED_TASKS,statuses)]
        self.logged=False
        self.f.db.exists.side_effect=lambda dt,filters: self.logged if dt=='Patch Log' else False if dt=='Field Task' else True
        self.f.get_all.side_effect=lambda dt,**kw: [row for row in self.rows if row.status not in ('Approved','Cancelled','Rejected') and not row.task_brief_version] if dt=='Field Task' else ['REVISIT']
        def update(dt,name,key,value=None,**kw):
            if dt=='Field Task':next(row for row in self.rows if row.name==name).status=value
        self.f.db.set_value.side_effect=update
        self.f.db.get_value.return_value='In Progress'
        def document(data):
            doc=MagicMock()
            def insert(**kw):
                if data['doctype']=='Patch Log':self.logged=True
            doc.insert.side_effect=insert
            return doc
        self.f.get_doc.side_effect=document
        self.workload=MagicMock()
        context=patch.dict(sys.modules,{'fieldpulse.fieldpulse.doctype.scout_profile.scout_profile':SimpleNamespace(recalculate_workload_and_availability=self.workload)})
        context.start();self.addCleanup(context.stop)

    def test_authorized_cancellation_preserves_records_and_is_one_time(self):
        self.authorized_site()
        self.m.assert_ready()
        self.assertTrue(all(row.status=='Rejected' for row in self.rows))
        self.workload.assert_called_once_with('SCOUT')
        self.f.db.set_value.assert_any_call('Field Request','PROJECT','status','Awaiting Assignment')
        comments=[call.args[0] for call in self.f.get_doc.call_args_list if call.args[0]['doctype']=='Comment']
        self.assertEqual(len(comments),2)
        self.assertIn('Previous status: Submitted',comments[1]['content'])
        self.assertIn('Submissions, evidence',comments[1]['content'])
        self.f.delete_doc.assert_not_called();self.f.db.delete.assert_not_called()
        self.f.db.set_value.reset_mock();self.m.assert_ready();self.f.db.set_value.assert_not_called()

    def test_unlisted_legacy_task_still_blocks_without_partial_cancellation(self):
        self.authorized_site()
        self.rows.append(SimpleNamespace(name='UNAPPROVED',status='Assigned',task_brief_version=None))
        with self.assertRaisesRegex(ValueError,'cutover blocked'):self.m.assert_ready()
        self.f.db.set_value.assert_not_called();self.assertFalse(self.logged)

    def test_approved_and_brief_tasks_are_not_cancelled(self):
        self.authorized_site(('Approved','Assigned'))
        self.rows[1].task_brief_version='NEW-BRIEF'
        self.m.assert_ready();self.f.db.set_value.assert_not_called()

    def test_a_reopened_assignment_is_not_cancelled_again(self):
        self.authorized_site();self.m.assert_ready();self.rows[0].status='Assigned'
        self.f.db.set_value.reset_mock()
        with self.assertRaisesRegex(ValueError,'cutover blocked'):self.m.assert_ready()
        self.f.db.set_value.assert_not_called()

    def test_failure_rolls_back_the_cancellation_unit(self):
        self.authorized_site();self.f.get_doc.side_effect=RuntimeError('Audit insert failed')
        with self.assertRaisesRegex(RuntimeError,'Audit insert'):self.m.assert_ready()
        self.f.db.rollback.assert_called_once_with(save_point='authorized_brief_cutover')
        self.assertFalse(self.logged)

    def test_cancelled_feed_is_site_and_owner_scoped(self):
        self.assertEqual(self.m.cancelled_legacy_tasks('SCOUT'),[])
        self.f.get_all.assert_not_called();self.f.local.site=self.m.AUTHORIZED_SITE
        self.m.cancelled_legacy_tasks('SCOUT','2026-10-28')
        filters=self.f.get_all.call_args.kwargs['filters']
        self.assertEqual(filters['scout_profile'],'SCOUT');self.assertEqual(filters['status'],['in',['Cancelled','Rejected']])
        self.assertEqual(filters['name'],['in',list(self.m.AUTHORIZED_TASKS)])
        self.assertEqual(filters['modified'],['>','2026-10-28'])
