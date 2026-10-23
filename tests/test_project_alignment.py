import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

class Doc(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def is_new(self): return self.get('_new', False)
    def has_permission(self, kind): return self.get('_allowed', True)
    def check_permission(self, kind):
        if not self.has_permission(kind): raise PermissionError(kind)

class AlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('alignment_test',Path(__file__).parents[1]/'fieldpulse/project_alignment.py')
        cls.m=importlib.util.module_from_spec(spec)
        fake=types.ModuleType('frappe'); fake.whitelist=lambda **kw:lambda fn:fn
        with patch.dict(sys.modules,{'frappe':fake}): spec.loader.exec_module(cls.m)
    def setUp(self):
        def throw(msg,exc=ValueError): raise exc(msg)
        self.api=types.SimpleNamespace(throw=throw,PermissionError=PermissionError,has_permission=Mock(return_value=True),get_doc=Mock(),get_all=Mock(),utils=types.SimpleNamespace(now=lambda:'2026-10-09',add_days=lambda d,n:date.fromisoformat(d)+timedelta(days=n)),db=types.SimpleNamespace(exists=Mock(return_value=False),get_value=Mock(return_value=None),set_value=Mock()))
        self.m.frappe=self.api
        self.source=Doc(name='DD1',creation='2026-10-01 12:00:00',deadline_preference='twoWeeks',category='land_property_check',summary='Project 1: Shop brief\n\nProject 2: Land brief',evidence_checklist=[Doc(evidence_item='Project 1 [SHOP · Garissa]: photos'),Doc(evidence_item='Project 2 [LAND · Nyandarua]: boundary')])
        self.request=Doc(name='FR1',diaspora_request='DD1',project_number=1,project_title='SHOP',county='Garissa',alignment_review=0,status='Awaiting Assignment',priority='Normal',deadline='2026-10-15',evidence_requirements='photos',field_brief='Shop brief',save=Mock())
    def test_projects_isolated(self):
        p=self.m.project_plan(self.source)
        self.assertFalse(p['issues']); self.assertEqual([r['county'] for r in p['projects']],['Garissa','Nyandarua'])
        self.assertEqual([r['request_type'] for r in p['projects']],['Business / Merchant Verification','Property Verification'])
        self.assertNotIn('Project 2','\n'.join(p['projects'][0]['evidence']))
    def test_label_separators(self):
        for sep in [' · ',' – ',' — ',' - ']:
            self.source.evidence_checklist=[Doc(evidence_item='Project 1 [SHOP'+sep+'Garissa County]: photos')]
            self.assertEqual(self.m.project_plan(self.source)['projects'][0]['county'],'Garissa')
    def test_deadline_preferences(self):
        for pref,want in [('twoWeeks','2026-10-15'),('oneWeek','2026-10-08'),('flexible',None),('specific','2026-11-01')]:
            self.source.deadline_preference=pref; self.source.deadline_date='2026-11-01'
            self.assertEqual(self.m.project_plan(self.source)['deadline'],want)
    def test_pending_projects(self):
        self.source.evidence_checklist=[]
        self.source.project_details=json.dumps([{'number':i+1,'description':s,'location_question_status':'needed'} for i,s in enumerate(['land in Turkana County','construction in Kitui County','salon in Kilifi County','document at Huduma Centre'])])
        p=self.m.project_plan(self.source)['projects']; self.assertEqual(len(p),4)
        self.assertEqual([r['county'] for r in p],['Turkana','Kitui','Kilifi','']); self.assertTrue(all(r['review'] for r in p))
    def test_conflicting_evidence(self):
        self.source.evidence_checklist.append(Doc(evidence_item='Project 1 [SHOP · Nairobi]: conflicting'))
        self.assertTrue(self.m.project_plan(self.source)['issues'])
        self.m.map_diaspora(self.source); self.assertEqual(self.source.alignment_review,1)
    def test_invalid_project_details(self):
        for s in ['broken','{}','[1]']:
            self.source.project_details=s
            with self.assertRaises(ValueError): self.m.project_plan(self.source)
    def test_scope_confirmation_does_not_require_note(self):
        self.request.scope_confirmed = 1
        self.m.fill_field_request(self.request, self.source, self.m.project_plan(self.source))
        self.assertEqual(self.request.alignment_review, 0)
        self.assertFalse(self.request.get('scope_review_note'))
    def test_scope_confirmation_still_requires_evidence(self):
        self.request.scope_confirmed = 1
        self.source.evidence_checklist = []
        self.source.project_details = json.dumps([{'number': 1, 'description': 'Shop in Garissa County'}])
        self.m.fill_field_request(self.request, self.source, self.m.project_plan(self.source))
        self.assertEqual(self.request.alignment_review, 1)
    def test_existing_deadline_and_isolated_brief(self):
        self.request.deadline='2026-12-01'; self.m.fill_field_request(self.request,self.source,self.m.project_plan(self.source))
        self.assertEqual(self.request.deadline,'2026-12-01'); self.assertEqual(self.request.customer_target_date,'2026-10-15'); self.assertNotIn('Land brief',self.request.field_brief)
    def test_assigned_request_not_split(self):
        self.request.project_number=None; self.request.status='Assigned'
        with self.assertRaises(ValueError): self.m.fill_field_request(self.request,self.source,self.m.project_plan(self.source))
    def test_task_scope_due_and_legacy(self):
        self.api.get_doc.return_value=self.request; task=Doc(_new=True,field_request='FR1')
        self.m.map_task(task); self.assertEqual(task.due_at,'2026-10-15 23:59:59'); self.assertEqual(task.task_brief,'Shop brief')
        task.due_at='2026-11-01 08:00:00'; self.m.map_task(task); self.assertEqual(task.due_at,'2026-11-01 08:00:00')
        self.m.map_task(Doc(_new=True,legacy_fp_task='FP1'))
        with self.assertRaises(ValueError): self.m.map_task(Doc(_new=True))
    def test_task_link_immutable(self):
        self.api.get_doc.return_value=self.request; self.api.db.get_value.return_value='OLD'
        with self.assertRaises(ValueError): self.m.map_task(Doc(name='T1',field_request='FR1'))
        with self.assertRaises(ValueError): self.m.map_task(Doc(name='T1'))
    def test_assignment_input_permissions_and_retries(self):
        self.api.get_doc.return_value=self.request
        for rows in ['broken',{},[],[None]]:
            with self.assertRaises(ValueError): self.m.assign_project_scouts('FR1',rows)
        self.api.has_permission.return_value=False
        with self.assertRaises(PermissionError): self.m.assign_project_scouts('FR1',[{'scout':'S1'}])
        self.api.has_permission.return_value=True; self.request.status='Assigned'; self.api.db.get_value.return_value='EXISTING'
        self.assertEqual(self.m.assign_project_scouts('FR1',[{'scout':'S1'}]),{'tasks':['EXISTING']})
        self.assertEqual(self.m.assign_project_scouts('FR1',[{'scout':'S1'},{'scout':'S2'}]),{'tasks':['EXISTING','EXISTING']})
    def test_manual_request_needs_no_customer_project_number(self):
        self.request.diaspora_request=None; self.request.project_number=None
        self.request.status='Assigned'; self.api.get_doc.return_value=self.request
        self.api.db.get_value.return_value='EXISTING'
        self.assertEqual(self.m.assign_project_scouts('FR1',[{'scout':'S1'}]),{'tasks':['EXISTING']})
        self.assertEqual(self.m.assign_project_scouts('FR1',[{'scout':'S1'},{'scout':'S2'}]),{'tasks':['EXISTING','EXISTING']})

    def test_partial_and_full_rollup(self):
        self.api.get_doc.side_effect=lambda dt,n:self.request if dt=='Field Request' else self.source
        for tasks,projects,want in [(['Approved','Assigned'],[(1,'In Progress')],'In Progress'),(['Approved'],[(1,'Completed')],'In Progress'),(['Approved'],[(1,'Completed'),(2,'Completed')],'Completed')]:
            self.api.get_all.side_effect=lambda dt,**kw:[Doc(status=s) for s in tasks] if dt=='Field Task' else [Doc(project_number=n,status=s) for n,s in projects]
            self.api.db.set_value.reset_mock(); self.m.rollup_tasks(Doc(field_request='FR1'))
            calls=self.api.db.set_value.call_args_list
            self.assertEqual([c.args[3] for c in calls if c.args[0]=='Diaspora Request'][-1],want)
    def test_cancelled_and_rejected_preserved(self):
        self.request.status='Cancelled'; self.api.get_doc.return_value=self.request; self.api.get_all.return_value=[Doc(status='Approved')]
        self.m.rollup_tasks(Doc(field_request='FR1')); self.api.db.set_value.assert_not_called()
        self.request.status='Assigned'; self.source.status='Rejected'; self.api.get_doc.side_effect=lambda dt,n:self.request if dt=='Field Request' else self.source
        self.api.get_all.side_effect=lambda dt,**kw:[Doc(status='Approved')] if dt=='Field Task' else [Doc(project_number=1,status='Completed'),Doc(project_number=2,status='Completed')]
        self.m.rollup_tasks(Doc(field_request='FR1'))
        self.assertFalse(any(c.args[0]=='Diaspora Request' for c in self.api.db.set_value.call_args_list))

if __name__=='__main__': unittest.main()
