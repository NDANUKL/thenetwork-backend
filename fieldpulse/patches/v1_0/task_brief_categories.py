"""Replace operational service selections without touching payments or recovery scripts."""
import frappe


def execute():
    from fieldpulse.task_briefs import CATEGORIES
    frappe.reload_doc('fieldpulse', 'doctype', 'diaspora_request', force=True)
    for status in ('needs_confirmation', 'out_of_scope'):
        for name in frappe.get_all('Diaspora Request', filters={'category': status}, pluck='name'):
            frappe.db.set_value('Diaspora Request', name, dict(category='custom_ground_verification',
                category_label=CATEGORIES['custom_ground_verification'], assessment_status=status), update_modified=False)
    mapping = {
        'Property Verification': 'land_property_check',
        'Construction Progress': 'construction_progress',
        'Business / Merchant Verification': 'business_asset_check',
        'Document / Receipt Verification': 'custom_ground_verification',
        'General Site Visit': 'custom_ground_verification',
        'School Attendance / Enrollment Verification': 'custom_ground_verification',
        'Clinic / Medical Visit Verification': 'custom_ground_verification',
    }
    for doctype in ('Field Request', 'Field Task'):
        frappe.reload_doc('fieldpulse', 'doctype', frappe.scrub(doctype), force=True)
        for row in frappe.get_all(doctype, fields=['name', 'request_type', 'service_category']):
            category = row.service_category if row.service_category in CATEGORIES else mapping.get(row.request_type)
            if category:
                frappe.db.set_value(doctype, row.name, dict(request_type=CATEGORIES[category], service_category=category), update_modified=False)
    # Existing questionnaire submissions/evidence retain their audit links.
    # No new dispatch can use those references: the assignment hook requires an
    # approved versioned Task Brief. Never touch retired DD script records here.
