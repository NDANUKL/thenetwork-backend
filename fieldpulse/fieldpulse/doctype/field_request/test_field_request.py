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
        scouts=[frappe.get_doc(dict(doctype='Scout Profile',scout_name='Alignment '+str(uuid4()),base_county='Garissa',availability_status='Available')).insert() for _ in range(3)]
        assignments=[dict(scout=scouts[0].name,responsibility='Exterior photographs'),dict(scout=scouts[1].name,responsibility='Inventory observations')]
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
