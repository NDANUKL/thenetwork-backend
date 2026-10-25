"""Strict visit-policy helpers, kept separate from historical geofence behaviour."""
from datetime import datetime
from fieldpulse.scout_library import decode
from fieldpulse.scout_protocol import arrival_result


def snapshot(task):
    return decode(task.get('client_request_snapshot'), {})


def strict(task):
    return snapshot(task).get('visit_workflow_version') == 2


def verified_arrival(response, task):
    data = snapshot(task)
    return arrival_result(decode(response.get('arrival_check_json'), {}), data.get('site_reference') or {}, strict=True)


def require_verified_arrival(response, task):
    if strict(task) and verified_arrival(response, task)['status'] != 'Inside':
        import frappe
        frappe.throw('Verify arrival at the assigned site before answering questions or capturing evidence')


def sample_is_contemporaneous(captured_at, sampled_at):
    try:
        captured = captured_at if isinstance(captured_at, datetime) else datetime.fromisoformat(str(captured_at).replace('Z', '+00:00'))
        sampled = sampled_at if isinstance(sampled_at, datetime) else datetime.fromisoformat(str(sampled_at).replace('Z', '+00:00'))
        return 0 <= (captured - sampled).total_seconds() <= 30
    except (ValueError, TypeError):
        return False
