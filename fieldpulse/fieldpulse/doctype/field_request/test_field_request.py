"""Real Frappe regression: bench --site <dev> run-tests --doctype 'Field Request'."""
import json
from uuid import uuid4
import frappe
from frappe.tests.utils import FrappeTestCase
from fieldpulse.project_alignment import assign_project_scouts

class TestFieldRequest(FrappeTestCase):
    def setUp(self):
        self.previous_user = frappe.session.user
        frappe.set_user('Administrator')
        self.addCleanup(frappe.set_user, self.previous_user)

    def source(self, **overrides):
        values = dict(doctype='Diaspora Request', submission_id=str(uuid4()), full_name='Alignment test',
                      email='alignment@example.test', original_brief='Two projects', summary='Project 1: Shop visit\n\nProject 2: Land visit',
                      deadline_preference='twoWeeks', category='land_property_check', category_label='Property',
                      classification_confidence='high', suggested_scouts=2, estimated_days=14,
                      recommendation_reason='Two projects', coverage_note='Separate counties', needs_human_review=0,
                      evidence_checklist=[dict(evidence_item='Project 1 [SHOP · Garissa]: photos'),
                                          dict(evidence_item='Project 2 [LAND · Nyandarua]: boundaries')])
        values.update(overrides)
        return frappe.get_doc(values).insert()

    def test_split_assignment_and_completion(self):
        source=self.source()
        rows=frappe.get_all('Field Request',filters={'diaspora_request':source.name},fields=['name','project_number','county','evidence_requirements'],order_by='project_number asc')
        self.assertEqual(len(rows),2)
        self.assertEqual([r.county for r in rows],['Garissa','Nyandarua'])
        self.assertNotIn('Project 2',rows[0].evidence_requirements)
        first=frappe.get_doc('Field Request',rows[0].name); first.save()
        self.assertEqual(frappe.db.count('Field Request',{'diaspora_request':source.name}),2)
        from fieldpulse.auth import register_field_agent
        from fieldpulse.scout_access import review_application
        scouts = []
        for _ in range(3):
            email = f'alignment-{uuid4().hex}@example.test'
            register_field_agent('Alignment Scout', email, f'Test!{uuid4().hex}', county='Garissa')
            application = frappe.db.get_value('Scout Application', {'email': email}, 'name')
            result = review_application(application, 'Approved')
            scouts.append(frappe.get_doc('Scout Profile', result['scout_profile']))
        assignments=[dict(scout=scouts[0].name),dict(scout=scouts[1].name)]
        tasks=assign_project_scouts(first.name,json.dumps(assignments))['tasks']
        self.assertEqual(assign_project_scouts(first.name,assignments)['tasks'],tasks)
        task=frappe.get_doc('Field Task',tasks[0])
        self.assertEqual(task.county,'Garissa'); self.assertEqual(task.project_number,1)
        self.assertTrue(str(task.due_at).endswith('23:59:59'))
        for name in tasks:
            task=frappe.get_doc('Field Task',name)
            for status in ['Accepted','In Progress','Submitted','Approved']:
                task.status=status; task.save()
            if name==tasks[0]: self.assertNotEqual(frappe.db.get_value('Field Request',first.name,'status'),'Completed')
        self.assertEqual(frappe.db.get_value('Field Request',first.name,'status'),'Completed')
        self.assertNotEqual(frappe.db.get_value('Diaspora Request',source.name,'status'),'Completed')
        name=assign_project_scouts(rows[1].name,[dict(scout=scouts[2].name)])['tasks'][0]
        task=frappe.get_doc('Field Task',name)
        for status in ['Accepted','In Progress','Submitted','Approved']:
            task.status=status; task.save()
        self.assertEqual(frappe.db.get_value('Diaspora Request',source.name,'status'),'Completed')

    def test_pending_projects(self):
        details=[dict(number=i+1,description=desc,location_question_status='needed') for i,desc in enumerate(['land in Turkana County','construction in Kitui County','salon in Kilifi County','document at Huduma Centre'])]
        source=self.source(evidence_checklist=[],project_details=json.dumps(details))
        rows=frappe.get_all('Field Request',filters={'diaspora_request':source.name},fields=['name','county','alignment_review'],order_by='project_number asc')
        self.assertEqual(len(rows),4); self.assertEqual([r.county or '' for r in rows],['Turkana','Kitui','Kilifi',''])
        self.assertTrue(all(r.alignment_review for r in rows))
        with self.assertRaises(frappe.ValidationError): assign_project_scouts(rows[0].name,[dict(scout='unconfirmed')])

    def test_structured_ids_three_projects_and_retries(self):
        details = [dict(id='stable-'+str(i), number=i, description='Display text ? '+str(i),
                        scope='Inspect only site '+str(i), county=county, eligibility='supported',
                        service_category='land_property_check', evidence_tasks=['Evidence '+str(i)])
                   for i, county in [(1,'Vihiga'),(2,'Kajiado'),(3,'Nairobi')]]
        source = self.source(project_details=json.dumps(details), project_contract_version=1,
                             evidence_checklist=[dict(evidence_item='Unrelated display formatting')])
        rows = frappe.get_all('Field Request',filters={'diaspora_request':source.name},
                              fields=['name','project_id','county','field_brief','evidence_requirements'],order_by='project_number asc')
        self.assertEqual(len(rows),3)
        self.assertEqual([row.project_id for row in rows],['stable-1','stable-2','stable-3'])
        self.assertEqual([row.county for row in rows],['Vihiga','Kajiado','Nairobi'])
        self.assertEqual(rows[1].field_brief,'Inspect only site 2')
        self.assertEqual(rows[1].evidence_requirements,'Evidence 2')
        source.save()
        again = frappe.get_all('Field Request',filters={'diaspora_request':source.name},pluck='name')
        self.assertEqual(set(again),{row.name for row in rows})

    def test_conversion_failure_reaches_transaction_owner(self):
        from unittest.mock import patch
        from fieldpulse.integrations.diaspora_request import create_field_request
        with patch('fieldpulse.integrations.diaspora_request.ensure_field_requests',side_effect=RuntimeError('Conversion failed')):
            with self.assertRaisesRegex(RuntimeError,'Conversion failed'):
                create_field_request(frappe._dict(name='synthetic-source'))

    def test_location_children_are_inserted_once_and_keep_source_identity(self):
        self.assertEqual(len([f for f in frappe.get_meta('Field Request').get_table_fields()
                              if f.fieldname == 'project_locations']), 1)
        project = dict(id='supplier-check', number=1, description='Check supplier stock',
                       county='Kajiado', eligibility='supported', service_category='business_asset_check',
                       evidence_tasks=['Photograph visible stock'])
        source = self.source(project_details=json.dumps([project]), project_contract_version=1,
            evidence_checklist=[], customer_sites=[dict(site_label='Project 1: Supplier',
                project_ids=json.dumps(['supplier-check']), location_mode='contact', county='Kajiado',
                area='Oloitoktok', contact_name='Supplier contact', contact_phone='0712345678',
                access_notes='Meet at the market entrance', pin_type='Site entrance')])
        target_name = frappe.db.get_value('Field Request', {'diaspora_request': source.name}, 'name')
        target = frappe.get_doc('Field Request', target_name)
        self.assertEqual(len(source.customer_sites), 1)
        self.assertEqual(len(target.project_locations), 1)
        original, copied = source.customer_sites[0], target.project_locations[0]
        self.assertNotEqual(original.name, copied.name)
        self.assertEqual(copied.source_site_id, original.name)
        self.assertEqual(copied.area, 'Oloitoktok')
        self.assertEqual(copied.contact_phone, '0712345678')
        source.save()
        target.reload()
        self.assertEqual([row.name for row in target.project_locations], [copied.name])
        self.assertEqual(frappe.db.count('DD Request Site', {'parent': target.name,
            'parenttype': 'Field Request', 'parentfield': 'project_locations'}), 1)
