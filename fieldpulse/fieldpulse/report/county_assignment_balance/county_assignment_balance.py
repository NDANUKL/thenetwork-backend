"""Permission-filtered allocations and county distribution, excluding cancellations."""
from collections import Counter
import frappe
from frappe.utils import getdate, add_days


def execute(filters=None):
    filters = filters or {}
    if not {'Field Operations Coordinator', 'Supervisor', 'Admin', 'System Manager'}.intersection(frappe.get_roles()):
        frappe.throw('Not permitted', frappe.PermissionError)
    query = {'status': ['!=', 'Cancelled']}
    start, end = filters.get('from_date'), filters.get('to_date')
    if start and end and getdate(start) > getdate(end):
        frappe.throw('Choose an end date on or after the start date')
    if start and end:
        query['assigned_at'] = ['between', [str(getdate(start)), str(getdate(end)) + ' 23:59:59.999999']]
    elif start:
        query['assigned_at'] = ['>=', str(getdate(start))]
    elif end:
        query['assigned_at'] = ['<', str(add_days(getdate(end), 1))]
    for key in ('field_request', 'county'):
        if filters.get(key): query[key] = filters[key]
    rows = frappe.get_list('Field Task', filters=query,
        fields=['name', 'task_number', 'field_request', 'project_title', 'county', 'scout_profile', 'status', 'assigned_at', 'started_at'],
        order_by='assigned_at desc', limit_page_length=0)
    names = list({row.scout_profile for row in rows})
    profiles = {row.name: row for row in frappe.get_list('Scout Profile',
        filters={'name': ['in', names]}, fields=['name', 'scout_name', 'base_county'], limit_page_length=0)} if names else {}
    for row in rows:
        profile = profiles.get(row.scout_profile, {})
        row['scout_name'] = profile.get('scout_name') or ''
        row['scout_county'] = profile.get('base_county') or 'County unconfirmed'
    if filters.get('scout_county'):
        rows = [row for row in rows if row['scout_county'] == filters['scout_county']]
    counts = Counter(row['scout_county'] for row in rows)
    columns = [dict(fieldname=key, label=label, fieldtype=kind, width=width, **({'options': options} if options else {}))
        for key, label, kind, width, options in [
            ('name', 'Field Task', 'Link', 170, 'Field Task'),
            ('task_number', 'Task number', 'Data', 120, None),
            ('field_request', 'Field Request', 'Link', 170, 'Field Request'),
            ('project_title', 'Project', 'Data', 220, None),
            ('county', 'Project County', 'Data', 150, None),
            ('scout_profile', 'Scout', 'Link', 160, 'Scout Profile'),
            ('scout_name', 'Scout name', 'Data', 170, None),
            ('scout_county', 'Scout County', 'Data', 150, None),
            ('status', 'Status', 'Data', 130, None),
            ('assigned_at', 'Assigned at', 'Datetime', 170, None),
            ('started_at', 'Started at (server)', 'Datetime', 170, None)]]
    chart = dict(type='bar', data=dict(labels=sorted(counts), datasets=[dict(name='Allocations', values=[counts[k] for k in sorted(counts)])]))
    message = 'One row per allocation; cancelled tasks excluded. County totals count allocations, not unique scouts. Scout counties reflect current profiles. Date filters use assignment date.'
    return columns, rows, message, chart
