import copy
import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from fieldpulse.recurring_rules import schedule, can_prepare, plan_transition

ROOT=Path(__file__).parents[1]


class CalendarTests(unittest.TestCase):
    def test_month_end_and_leap_year_keep_original_anchor(self):
        rows=schedule('Monthly','2028-01-31',3,window_days=0,today=date(2028,1,1))
        self.assertEqual([r['due_date'] for r in rows],['2028-01-31','2028-02-29','2028-03-31'])

    def test_custom_terms_use_actual_dates_not_quarter_assumptions(self):
        rows=schedule('Specific dates',dates=['2027-09-03','2027-01-06','2027-05-04'],today=date(2026,10,25))
        self.assertEqual([r['sequence'] for r in rows],[1,2,3])
        self.assertEqual(rows[0]['window_end'],'2027-01-12')

    def test_invalid_and_overlapping_schedules(self):
        cases=[dict(frequency='Monthly',start_date='2027-02-30',visits=2),
            dict(frequency='Weekly',start_date='2027-01-01',visits=2),
            dict(frequency='Monthly',start_date='2026-10-24',visits=2),
            dict(frequency='Monthly',start_date='2027-01-01',visits=True),
            dict(frequency='Monthly',start_date='2027-01-01',visits=25),
            dict(frequency='Every 3 months',start_date='2027-01-01',visits=10),
            dict(frequency='Specific dates',dates=['2027-01-01','2027-01-01']),
            dict(frequency='Specific dates',dates=['2027-01-01','2027-01-05']),
            dict(frequency='Specific dates',dates=[])]
        for case in cases:
            with self.subTest(case=case),self.assertRaises(ValueError):schedule(**case,today=date(2026,10,25))

    def test_window_boundaries_and_preparation_gate(self):
        row=dict(status='Access confirmed',due_date='2026-11-08',window_end='2026-11-14',access_confirmed_at='2026-10-25')
        self.assertTrue(can_prepare('Active',row,date(2026,10,25)))
        for status,when in [('Paused',date(2026,10,25)),('Active',date(2026,10,24)),('Active',date(2026,11,15))]:
            self.assertFalse(can_prepare(status,row,when))
        self.assertFalse(can_prepare('Active',{**row,'request':'existing'},date(2026,10,25)))
        self.assertFalse(can_prepare('Active',{**row,'access_confirmed_at':None},date(2026,10,25)))

    def test_customers_cannot_approve_plans_and_terminal_states_do_not_resume(self):
        self.assertEqual(plan_transition('Active','Pause'),'Paused')
        self.assertEqual(plan_transition('Paused','Resume'),'Active')
        self.assertEqual(plan_transition('Pending review','Approve',staff=True),'Active')
        for status,action in [('Pending review','Approve'),('Cancelled','Resume'),('Completed','Resume')]:
            with self.assertRaises(ValueError):plan_transition(status,action)


class Record(dict):
    def __getattr__(self,key):return self.get(key)
    def __setattr__(self,key,value):self[key]=value
    def set(self,key,value):self[key]=value


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock();self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.PermissionError=PermissionError;self.f.ValidationError=ValueError
        self.f.throw.side_effect=lambda message,*args:(_ for _ in ()).throw(PermissionError(message))
        self.f.flags=Record();self.f.session=Record(user='coordinator@example.com')
        self.f.utils.today=lambda:'2026-10-25';self.f.utils.now_datetime=lambda:datetime(2026,10,25,12)
        self.f.utils.get_datetime=lambda value:datetime.fromisoformat(str(value))
        self.f.get_roles.return_value=['Field Operations Coordinator']
        spec=importlib.util.spec_from_file_location('recurring_test_runtime',ROOT/'fieldpulse/recurring.py')
        self.m=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':self.f}):spec.loader.exec_module(self.m)
        self.plan=Record(name='plan-1',doctype=self.m.PLAN,customer_account='account-1',source_request='DD-1',status='Active',history='[]',modified='2026-10-25 12:00:00',save=MagicMock(),check_permission=MagicMock())
        self.visit=Record(name='visit-1',doctype=self.m.OCCURRENCE,plan='plan-1',status='Scheduled',due_date='2026-11-01',window_end='2026-11-07',history='[]',modified='2026-10-25 12:00:00',save=MagicMock())
        self.f.get_doc.side_effect=lambda dt,name:self.plan if dt==self.m.PLAN else self.visit
        self.f.db.exists.return_value=True
        self.f.get_all.return_value=[]

    def act(self,action,visit=None,notes='',customer='account-1',version=None,id='action-id-0001'):
        return self.m.action_impl('plan-1',action,version or '2026-10-25 12:00:00',id,visit,notes,customer=customer)

    def test_ownership_stale_versions_and_server_only_approval(self):
        with self.assertRaises(PermissionError):self.act('Pause',customer='someone-else')
        with self.assertRaisesRegex(ValueError,'changed'):self.act('Pause',version='2026-10-24 12:00:00')
        self.plan.status='Pending review'
        with self.assertRaisesRegex(ValueError,'not available'):self.act('Approve')

    def test_retry_same_action_is_safe_but_changed_payload_is_rejected(self):
        self.act('Pause');self.assertEqual(self.plan.status,'Paused')
        self.plan.modified='2026-10-25 12:05:00'
        self.act('Pause')
        self.assertEqual(len(json.loads(self.plan.history)),1)
        with self.assertRaisesRegex(ValueError,'changed instructions'):self.act('Pause',notes='changed')

    def test_confirm_access_does_not_create_a_task_or_charge(self):
        self.act('Confirm access','visit-1','Caretaker will meet the scout')
        self.assertEqual(self.visit.status,'Access confirmed')
        self.assertEqual(self.visit.access_notes,'Caretaker will meet the scout')
        self.assertFalse(self.visit.request)
        self.f.get_doc.assert_any_call(self.m.OCCURRENCE,'visit-1')
        self.assertFalse(any(isinstance(c.args[0],dict) and c.args[0].get('doctype') in ['Field Task','DD Payment','DD Quotation'] for c in self.f.get_doc.call_args_list))

    def test_skipping_does_not_consume_other_dates_and_prepared_visits_stay_locked(self):
        self.act('Skip','visit-1','Client unavailable')
        self.assertEqual(self.visit.status,'Skipped')
        self.visit.status='Prepared';self.visit.request='DD-NEW'
        with self.assertRaisesRegex(ValueError,'unprepared'):self.act('Skip','visit-1','Change date',id='action-id-0002')

    def test_cancel_preserves_prepared_requests_and_schedule_dates(self):
        original=(self.visit.due_date,self.visit.window_end)
        self.f.get_all.return_value=['visit-1']
        self.act('Cancel')
        self.assertEqual(self.plan.status,'Cancelled');self.assertEqual(self.visit.status,'Cancelled')
        self.assertEqual(original,(self.visit.due_date,self.visit.window_end))
        filters=self.f.get_all.call_args.kwargs['filters']
        self.assertNotIn('Prepared',filters['status'][1])

    def test_retired_or_unconfirmed_access_cannot_prepare(self):
        with self.assertRaisesRegex(ValueError,'confirm access'):self.m.prepare_occurrence(self.plan,self.visit)
        self.visit.status='Access confirmed';self.visit.access_confirmed_at='2026-10-25'
        self.plan.status='Paused'
        with self.assertRaisesRegex(ValueError,'confirm access'):self.m.prepare_occurrence(self.plan,self.visit)

    def test_model_writes_are_service_only_and_provenance_cannot_be_cleared(self):
        with self.assertRaisesRegex(ValueError,'cannot be edited'):self.m.validate_document(self.plan)
        with self.m.writing():self.m.validate_document(self.plan)
        self.assertFalse(self.f.flags.get('dd_recurring_write'))
        previous=Record(recurring_plan='plan-1',recurring_occurrence='visit-1',recurring_source='DD-1')
        doc=Record(recurring_plan=None,recurring_occurrence=None,is_new=lambda:False,get_doc_before_save=lambda:previous)
        with self.assertRaisesRegex(ValueError,'provenance'):self.m.guard_request(doc)

    def test_prepare_reuses_scope_as_an_unapproved_brief_in_new_request(self):
        from fieldpulse.task_briefs import brief_digest
        content=json.loads((ROOT/'tests/fixtures/task-brief-v1.json').read_text())['brief']
        target=Record(name='FR-NEW',project_id='project-1',field_brief='Inspect the roof',
            evidence_requirements='Roof photos',save=MagicMock())
        project={key:target.get(key) for key in self.m.CONTEXT}
        project.update(project_id='project-1',task_brief=content,fingerprint=brief_digest(content))
        source=dict(original_brief='Inspect my roofing',summary='Roofing',customer_sites=[dict(site_label='Site 1',access_notes='Gate')])
        snapshot=dict(source=source,projects=[project])
        self.plan.scope_snapshot=json.dumps(snapshot);self.plan.scope_hash=self.m.digest(snapshot)
        self.visit.status='Access confirmed';self.visit.access_confirmed_at='2026-10-25';self.visit.access_notes='Meet caretaker'
        created=[]
        def get_doc(dt,name=None):
            if isinstance(dt,dict):
                created.append(copy.deepcopy(dt));return Record(**dt,name='DD-NEW',insert=MagicMock())
            if dt=='DD Customer Account':return Record(email_verified=1,user='client@example.com')
            if dt=='Field Request':return target
            return self.plan
        self.f.get_doc.side_effect=get_doc
        self.f.get_all.side_effect=lambda dt,**kw:['FR-NEW'] if dt=='Field Request' else [];self.f.db.get_value.return_value=True
        with patch.dict(sys.modules,{'fieldpulse.beta_access':types.SimpleNamespace(require_access=lambda doc:None)}):
            self.assertEqual(self.m.prepare_occurrence(self.plan,self.visit),'DD-NEW')
        self.assertEqual(self.visit.status,'Prepared')
        self.assertEqual(created[0]['status'],'New')
        self.assertEqual(created[0]['submission_id'],'recurring:visit-1')
        self.assertEqual(created[0]['deadline_date'],'2026-11-07')
        self.assertEqual(created[0]['recurring_plan'],'plan-1')
        self.assertNotIn('payments',created[0]);self.assertNotIn('report',created[0])
        self.assertEqual(created[0]['customer_sites'][0]['confirmation_status'],'Needs confirmation')
        self.assertEqual(created[1]['doctype'],'DD Task Brief')
        self.assertEqual(created[1]['status'],'Draft')
        self.assertEqual(json.loads(created[1]['content_json']),content)
        self.assertFalse(target.approved_task_brief)
        self.assertEqual(source['customer_sites'][0]['access_notes'],'Gate')
        self.assertEqual(self.m.prepare_occurrence(self.plan,self.visit),'DD-NEW')
        self.assertEqual(len(created),2)

    def test_business_errors_rollback_before_becoming_customer_messages(self):
        self.m.account=lambda:'account-1'
        result=self.m.act('plan-1','Pause','2026-10-24 12:00:00','action-id-0001')
        self.assertFalse(result['success'])
        self.f.db.rollback.assert_called_with(save_point='recurring_api')

    def test_creation_is_idempotent_and_duplicate_open_plans_are_blocked(self):
        store={}
        source=Record(name='DD-1',summary='Check the field',category='land_property_check',reload=MagicMock())
        self.m.account=lambda:'account-1';self.m.source_snapshot=lambda doc:dict(source={},projects=[],quote={})
        def exists(dt,value):
            if isinstance(value,str):return (dt,value) in store
            return any(kind==dt and all(record.get(k) in v[1] if isinstance(v,list) else record.get(k)==v for k,v in value.items()) for (kind,_),record in store.items())
        def get_doc(value,name=None):
            if isinstance(value,str):return store[value,name]
            doc=Record(**value,creation='2026-10-25 12:00:00',modified='2026-10-25 12:00:00')
            def insert(**kwargs):
                doc.name=kwargs['set_name'];store[doc.doctype,doc.name]=doc;return doc
            doc.insert=insert;return doc
        self.f.db.exists.side_effect=exists;self.f.get_doc.side_effect=get_doc
        payment=types.SimpleNamespace(_owned=lambda reference:source)
        with patch.dict(sys.modules,{'fieldpulse.payments':payment}):
            args=dict(reference='DD-1',frequency='Monthly',submission_id='create-id-0001',start_date='2027-01-01',visits=6,window_days=6)
            first=self.m.create(**args);second=self.m.create(**args)
            self.assertEqual(first['plan']['name'],second['plan']['name'])
            self.assertEqual(len(store),7)
            changed=self.m.create(**{**args,'visits':7})
            self.assertFalse(changed['success'])
            duplicate=self.m.create(**{**args,'submission_id':'create-id-0002'})
            self.assertFalse(duplicate['success']);self.assertIn('open recurring plan',duplicate['error'])
        self.assertEqual(len(store),7)
        self.assertTrue(any('tabDiaspora Request' in call.args[0] and 'FOR UPDATE' in call.args[0] for call in self.f.db.sql.call_args_list))

    def test_approval_rechecks_scope_and_a_paused_visit_cannot_be_prepared(self):
        self.plan.status='Pending review';self.plan.first_visit='2026-11-01';self.plan.scope_hash='old'
        self.m.source_snapshot=lambda doc:dict(changed='new question')
        with self.assertRaisesRegex(ValueError,'source scope changed'):
            self.act('Approve',notes='Availability and per-visit costs reviewed',customer=None)
        self.assertEqual(self.plan.status,'Pending review')

    def test_scheduler_marks_expired_paused_dates_missed_without_catchup(self):
        self.plan.status='Paused';self.visit.due_date='2026-10-18';self.visit.window_end='2026-10-24'
        self.f.conf={'dd_native_handover_approved':True};self.f.db.get_value.return_value=self.plan.name
        self.f.db.sql.side_effect=lambda query,*args,**kw:[Record(name=self.visit.name)] if 'SELECT o.name' in query else []
        self.f.get_all.side_effect=lambda dt,**kw:[self.visit.name] if kw.get('pluck')=='name' else [self.visit.status]
        self.m.process_due()
        self.assertEqual(self.visit.status,'Missed')
        self.assertFalse(self.visit.request)
        self.assertEqual(self.visit.due_date,'2026-10-18')
        self.f.db.commit.assert_called_once()


if __name__=='__main__':unittest.main()


class SiteSnapshotTests(unittest.TestCase):
    setUp=RuntimeTests.setUp
    act=RuntimeTests.act
    def test_scope_copies_verified_site_inputs_but_not_dispatch_approval(self):
        source=Record(name='source-site',site_label='Field',project_ids='["project-1"]',latitude=None,longitude=None,access_notes='Old instructions')
        operational=Record(source_site_id='source-site',site_label='Field',latitude=-1.2,longitude=36.8,access_notes='Verified gate',confirmation_status='Confirmed for dispatch')
        result=self.m.snapshot_sites([source],[operational])[0]
        self.assertEqual(result['latitude'],-1.2)
        self.assertEqual(result['project_ids'],'["project-1"]')
        self.assertEqual(result['access_notes'],'Verified gate')
        self.assertNotIn('confirmation_status',result)
        self.assertIsNone(source.latitude)
        with self.assertRaisesRegex(ValueError,'conflicting'):
            self.m.snapshot_sites([source],[operational,Record(**{**operational,'longitude':37.0})])

    def test_skipping_the_last_date_finishes_the_plan(self):
        self.f.get_all.return_value=['Skipped']
        self.act('Skip','visit-1','No visit required')
        self.assertEqual(self.plan.status,'Completed')
