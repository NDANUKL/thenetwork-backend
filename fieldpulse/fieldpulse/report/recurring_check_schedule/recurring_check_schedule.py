"""Scheduled demand and actual visit outcomes; no forecast is counted as revenue."""
import frappe
from fieldpulse.recurring_rules import day


def execute(filters=None):
    filters=filters or {}
    if not {'System Manager','Field Operations Coordinator','Finance'}.intersection(frappe.get_roles()):
        frappe.throw('Not permitted',frappe.PermissionError)
    start=str(day(filters.get('from_date') or frappe.utils.today()))
    end=str(day(filters.get('to_date') or frappe.utils.add_months(start,12)))
    if end<start: frappe.throw('Choose an end date after the start date')
    columns=[
        dict(fieldname='month',label='Scheduled month',fieldtype='Data',width=130),
        dict(fieldname='due_date',label='Visit date',fieldtype='Date',width=110),
        dict(fieldname='window_end',label='Window ends',fieldtype='Date',width=110),
        dict(fieldname='service_category',label='Service',fieldtype='Data',width=180),
        dict(fieldname='status',label='Visit outcome / stage',fieldtype='Data',width=170),
        dict(fieldname='plan_status',label='Plan status',fieldtype='Data',width=130),
        dict(fieldname='plan',label='Recurring plan',fieldtype='Link',options='DD Recurring Plan',width=180),
        dict(fieldname='request',label='Prepared request',fieldtype='Link',options='Diaspora Request',width=180),
        dict(fieldname='request_status',label='Request status',fieldtype='Data',width=140),
    ]
    rows=frappe.db.sql("""SELECT DATE_FORMAT(o.due_date,'%%Y-%%m') AS month,
        o.due_date,o.window_end,o.service_category,o.status,p.status AS plan_status,o.plan,o.request,r.status AS request_status
        FROM `tabDD Recurring Occurrence` o JOIN `tabDD Recurring Plan` p ON p.name=o.plan
        LEFT JOIN `tabDiaspora Request` r ON r.name=o.request
        WHERE o.due_date BETWEEN %(start)s AND %(end)s ORDER BY o.due_date,o.plan,o.sequence""",dict(start=start,end=end),as_dict=True)
    return columns,rows,None,None,None
