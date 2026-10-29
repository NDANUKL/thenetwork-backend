"""Queue application alerts transactionally through Frappe's Email Queue."""
import frappe
from frappe.utils import get_url_to_form


def application_received(doc):
    users = frappe.get_all('Has Role', filters={
        'role': 'Field Operations Coordinator', 'parenttype': 'User'
    }, pluck='parent')
    recipients = frappe.get_all('User', filters={
        'name': ['in', users], 'enabled': 1, 'user_type': 'System User'
    }, pluck='email') if users else []
    recipients = sorted({email for email in recipients if email})
    if not recipients:
        frappe.log_error(title='Scout application notification',
                         message='No enabled coordinator email recipient is configured.')
        return
    html = frappe.render_template(
        'fieldpulse/templates/emails/scout_application.html',
        dict(applicant_name=doc.full_name or 'New applicant',
             county=doc.county or 'County unconfirmed',
             review_link=get_url_to_form('Scout Application', doc.name)),
    )
    frappe.sendmail(
        recipients=recipients,
        subject='New scout application',
        message=html,
        reference_doctype='Scout Application', reference_name=doc.name,
        delayed=True,
    )
