"""
Shared constants for the FieldPulse app.

NOTE ON SCOPE: FP Agent, FP Attachment, and FP Task currently carry
extra fields (trust_tier, kyc_status, bond_status, routing_mode,
consent_status, verification_nonce, assignment_source, dispute_status,
nonce, liveness_status, duplicate_check_status) that come from Isaac's
dual-marketplace / Trust Market architecture, not the original
internship-plan scope. The TRUST_MARKET section below exists only to
keep this file consistent with the schema as it stands on disk right
now. It's grouped separately, on purpose, so it's easy to delete if
the scope decision goes the other way.
"""

ROLES = [
    "Field Agent",
    "Supervisor",
    "Admin",
]

# Matches the Select options on FP Question.question_type exactly.
QUESTION_TYPES = [
    {"value": "short_text", "label": "Short text"},
    {"value": "long_text", "label": "Long text"},
    {"value": "number", "label": "Number"},
    {"value": "date_time", "label": "Date / time"},
    {"value": "single_select", "label": "Single select"},
    {"value": "multi_select", "label": "Multi-select"},
    {"value": "yes_no", "label": "Yes / No"},
    {"value": "rating_scale", "label": "Rating / scale"},
    {"value": "conditional_logic", "label": "Conditional / skip logic"},
    {"value": "gps_point", "label": "GPS point"},
    {"value": "photo", "label": "Photo"},
    {"value": "file_attachment", "label": "File attachment"},
    {"value": "signature", "label": "Signature"},
]

QUESTION_TYPE_VALUES = [q["value"] for q in QUESTION_TYPES]

# Question types whose answers go through the attachment upload
# pipeline rather than the structured response batch.
ATTACHMENT_QUESTION_TYPES = {"photo", "file_attachment", "signature"}

TASK_STATUSES = [
    "Draft",
    "Assigned",
    "In Progress",
    "Submitted",
    "Approved",
    "Rejected",
    "Cancelled",
]

TASK_RESPONSE_STATUSES = [
    "Draft",
    "Submitted",
    "Accepted",
    "Rejected",
]

QUESTIONNAIRE_STATUSES = [
    "Draft",
    "Published",
    "Archived",
]

GEOFENCE_STATUSES = [
    "Unknown",
    "Inside",
    "Outside",
    "Invalid GPS",
]

QA_STATUSES = [
    "Pending",
    "Passed",
    "Failed",
    "Needs Review",
]

SYNC_LOG_DIRECTIONS = [
    "Pull",
    "Push",
    "Attachment Upload",
    "Mixed",
]

SYNC_LOG_STATUSES = [
    "Success",
    "Partial Success",
    "Failed",
]

DEFAULT_GEOFENCE_TOLERANCE_M = 50

# --- Trust Market / dual-marketplace fields (pending scope decision) ---

TRUST_TIERS = ["Tier 1", "Tier 2", "Tier 3"]

KYC_STATUSES = ["Not Started", "Pending", "Verified", "Rejected", "Expired"]

BOND_STATUSES = ["Not Required", "Pending", "Active", "Slashed", "Released"]

ROUTING_MODES = ["Trust", "Outcome"]

CONSENT_STATUSES = ["Pending", "Granted", "Declined", "Revoked", "Not Required"]

ASSIGNMENT_SOURCES = ["Manual", "Auto Match"]

DISPUTE_STATUSES = ["None", "Open", "Resolved"]
