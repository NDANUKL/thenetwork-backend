"""Coordinator-owned, immutable approved Task Brief versions."""
import json
import frappe
from frappe.model.document import Document
from fieldpulse.task_briefs import validate_brief, brief_digest


class DDTaskBrief(Document):
    def validate(self):
        initial = self.is_new() and self.status == 'Draft' and frappe.flags.dd_initial_brief_project == self.project
        if not initial and not {'System Manager', 'Field Operations Coordinator'}.intersection(frappe.get_roles()):
            frappe.throw('Only coordinators may edit or approve Task Briefs', frappe.PermissionError)
        if not initial:
            frappe.get_doc('Field Request', self.project).check_permission('write')
        previous = self.get_doc_before_save() if not self.is_new() else None
        if previous and previous.status == 'Approved':
            frappe.throw('Approved Task Briefs are immutable; create a new draft version')
        if previous and (self.project != previous.project or self.version != previous.version):
            frappe.throw('The project and version cannot be changed')
        if self.is_new():
            frappe.db.sql('SELECT name FROM `tabField Request` WHERE name=%s FOR UPDATE', [self.project])
            self.version = int(frappe.db.get_value('DD Task Brief', {'project': self.project}, 'version', order_by='version desc') or 0) + 1
        if previous and self.supersedes != previous.supersedes:
            frappe.throw('Previous version provenance cannot be changed')
        if self.supersedes:
            source = frappe.get_doc('DD Task Brief', self.supersedes)
            if source.project != self.project or source.status != 'Approved' or source.version >= self.version:
                frappe.throw('Previous version must be an earlier approved brief for this project')
        try:
            content = validate_brief(self.content_json)
        except (TypeError, ValueError) as error:
            frappe.throw(str(error))
        if self.status not in {'Draft', 'Approved'}:
            frappe.throw('Choose Draft or Approved')
        self.title = content['title']
        self.category = content['category']
        self.content_json = json.dumps(content, ensure_ascii=False)
        self.content_hash = brief_digest(content)
        if self.status == 'Approved':
            if content['review_required'] or not content['checks']:
                frappe.throw('Resolve flagged scope or safety issues and supply checks before approval')
            if not content['deliverables']:
                frappe.throw('Specify the expected deliverables before approval')
            self.approved_by = frappe.session.user
            self.approved_at = frappe.utils.now_datetime()
        else:
            self.approved_by = None
            self.approved_at = None

    def on_trash(self):
        if self.status == 'Approved':
            frappe.throw('Approved Task Brief versions are retained for audit')

    def on_update(self):
        if self.status == 'Approved':
            project = frappe.get_doc('Field Request', self.project)
            project.approved_task_brief = self.name
            project.save()


@frappe.whitelist(methods=['POST'])
def revise(brief):
    source = frappe.get_doc('DD Task Brief', brief)
    source.check_permission('read')
    if source.status != 'Approved':
        frappe.throw('Edit the existing draft before creating another version')
    draft = frappe.get_doc(dict(doctype='DD Task Brief', project=source.project,
        status='Draft', content_json=source.content_json, supersedes=source.name))
    draft.insert()
    return draft.name
