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
    from fieldpulse.email_branding import render_email
    html = render_email(title='New scout application', eyebrow='COORDINATOR UPDATE',
        body=f"A new scout application is ready for review.<br><strong>{frappe.utils.escape_html(doc.full_name or 'New applicant')}</strong><br>{frappe.utils.escape_html(doc.county or 'County unconfirmed')}",
        origin=frappe.utils.get_url(), link=get_url_to_form('Scout Application', doc.name),
        label='Review application', note='Sign in to Frappe to review this application. You received this email because you are a Field Operations Coordinator.',
        body_is_html=True)
    frappe.sendmail(
        recipients=recipients,
        subject='New scout application',
        message=html,
        reference_doctype='Scout Application', reference_name=doc.name,
        delayed=True,
    )
