"""Frappe event wiring; each production event has a single native owner."""
from fieldpulse.native_ownership import owned_event

@owned_event("DD Project Metadata", "DD Submitted Project Contract")
def map_diaspora(doc, method=None):
    from fieldpulse.project_alignment import map_diaspora as run
    return run(doc, method)

@owned_event("DD Field Project Mapping", "DD Field Location Gate")
def map_field_request(doc, method=None):
    from fieldpulse.project_alignment import map_field_request as run
    return run(doc, method)

@owned_event("DD Field Project Expansion", "DD Location Navigation Sync")
def ensure_field_requests(doc, method=None):
    from fieldpulse.project_alignment import ensure_field_requests as run
    return run(doc, method)

@owned_event("DD Task Project Mapping")
def map_task(doc, method=None):
    from fieldpulse.project_alignment import map_task as run
    return run(doc, method)

@owned_event("DD Payment Deposit Gate")
def require_deposit(doc, method=None):
    from fieldpulse.payments import require_deposit as run
    return run(doc, method)

@owned_event("DD Quotation Validation")
def validate_quote(doc, method=None):
    from fieldpulse.payments import validate_quote as run
    return run(doc, method)

@owned_event("DD Dispute Validation")
def validate_dispute(doc, method=None):
    from fieldpulse.commerce import validate_dispute as run
    return run(doc)

@owned_event("DD Service Report Validation")
def validate_report(doc, method=None):
    from fieldpulse.commerce import validate_report as run
    return run(doc)

@owned_event("DD Pesapal Reconciliation")
def reconcile():
    from fieldpulse.payments import reconcile as run
    return run()

@owned_event("DD Field Project Expansion")
def sync_task_navigation(doc, method=None):
    from fieldpulse.project_locations import sync_task_navigation as run
    return run(doc, method)
