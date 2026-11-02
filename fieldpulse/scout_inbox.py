"""Recipient-scoped mobile inbox for every Notification Log category."""
from html.parser import HTMLParser
import frappe
from fieldpulse.mobile_datetime import site_datetime_iso


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        elif tag in ('br','p','div','li'):self.parts.append(' ')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
        elif tag in ('p','div','li'):self.parts.append(' ')
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)


def plain(value,limit):
    parser=PlainText();parser.feed(str(value or ''))
    return ' '.join(''.join(parser.parts).split())[:limit]


def mark_notification_read(notification_id):
    """Mark one of the authenticated scout's notifications as read."""
    user=frappe.session.user
    if user=='Guest' or not frappe.db.exists('Scout Profile',{'user':user}):
        frappe.throw('Sign in as a scout.',frappe.PermissionError)
    if not isinstance(notification_id,str) or not notification_id or len(notification_id)>140:
        frappe.throw('A valid notification ID is required')
    row=frappe.db.get_value('Notification Log',{'name':notification_id,'for_user':user},['name','read'],as_dict=True)
    if not row:
        frappe.throw('Notification not found.',frappe.PermissionError)
    if not row.get('read'):
        frappe.db.set_value('Notification Log',notification_id,'read',1,update_modified=False)
    return {'id':notification_id,'read':True}


def notification_payload():
    user=frappe.session.user
    if user=='Guest' or not frappe.db.exists('Scout Profile',{'user':user}):
        frappe.throw('Sign in as a scout.',frappe.PermissionError)
    rows=frappe.get_all('Notification Log',filters={'for_user':user},
        fields=['name','subject','email_content','creation','read','document_type','document_name'],
        order_by='creation desc, name desc',limit_page_length=100)
    result=[]
    for row in rows:
        subject=plain(row.get('subject'),160)
        if not subject:continue
        doctype,name=row.get('document_type'),row.get('document_name') or ''
        target='task' if doctype=='Field Task' else 'earnings' if doctype in ('DD Scout Offer','DD Scout Expense','DD Scout Earning','DD Scout Payout','DD Payout Beneficiary','DD Earning Adjustment') else 'privacy' if doctype=='Scout Data Request' else 'profile' if doctype in ('Scout Profile','Scout Application','User') else 'none'
        kind=subject
        if target=='task':
            if subject.startswith(('Correction requested:', 'Rework required:')):kind='Review feedback updated'
            elif subject.startswith('Site revisit assigned'):kind='New assignment'
            elif subject=='Revisit authorization updated':kind='Revisit authorized'
        result.append(dict(id=row['name'],subject=subject,body=plain(row.get('email_content'),2000),
            event_kind=kind,created_at=site_datetime_iso(row['creation']),read=bool(row.get('read')),
            target_type=target,target_id=name))
    return result
