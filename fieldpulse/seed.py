import frappe


def seed_demo_data():
    """Create a small Trust Market demo corridor for local testing."""
    location = _ensure_doc(
        "FP Location",
        "DEMO-NAIROBI-001",
        {
            "location_code": "DEMO-NAIROBI-001",
            "location_name": "Demo Nairobi Field Site",
            "latitude": -1.286389,
            "longitude": 36.817223,
            "geofence_radius_m": 50,
            "status": "Active",
        },
    )

    agent = _ensure_by_field(
        "FP Agent",
        "agent_code",
        "AGENT-001",
        {
            "agent_code": "AGENT-001",
            "full_name": "Demo Field Agent",
            "status": "Active",
            "trust_tier": "Tier 1",
            "kyc_status": "Verified",
            "bond_status": "Not Required",
            "default_location": location.name,
            "service_latitude": -1.286389,
            "service_longitude": 36.817223,
            "service_radius_km": 10,
        },
    )

    questionnaire = _ensure_by_field(
        "FP Questionnaire",
        "questionnaire_code",
        "STORE-CHECK-V1",
        {
            "questionnaire_code": "STORE-CHECK-V1",
            "title": "Store Check",
            "version": 1,
            "status": "Published",
            "description": "Demo questionnaire for offline field verification.",
            "published_at": frappe.utils.now(),
        },
    )

    _seed_questionnaire_questions(questionnaire)

    _ensure_doc(
        "FP Task",
        "TASK-DEMO-001",
        {
            "task_code": "TASK-DEMO-001",
            "agent": agent.name,
            "location": location.name,
            "questionnaire": questionnaire.name,
            "questionnaire_version": 1,
            "intent_template_code": "store_check",
            "routing_mode": "Trust",
            "consent_status": "Granted",
            "verification_nonce": frappe.generate_hash(length=12),
            "assignment_source": "Manual",
            "status": "Assigned",
            "priority": "Normal",
            "qa_status": "Pending",
            "dispute_status": "None",
            "assigned_at": frappe.utils.now(),
            "server_updated_at": frappe.utils.now(),
        },
    )


def _seed_questionnaire_questions(questionnaire):
    questions = [
        {
            "question_code": "store_open",
            "label": "Is the store open?",
            "question_type": "yes_no",
            "sequence": 1,
            "required": 1,
            "options": [("yes", "Yes"), ("no", "No")],
        },
        {
            "question_code": "stock_count",
            "label": "How many promoted items are visible?",
            "question_type": "number",
            "sequence": 2,
            "required": 1,
            "validation_json": '{"min": 0, "max": 1000, "decimals": 0}',
        },
        {
            "question_code": "shelf_photo",
            "label": "Capture shelf photo",
            "question_type": "photo",
            "sequence": 3,
            "required": 1,
            "validation_json": '{"min_count": 1, "max_count": 3, "allowed_mime_types": ["image/jpeg", "image/png"]}',
        },
        {
            "question_code": "gps_capture",
            "label": "Confirm visit location",
            "question_type": "gps_point",
            "sequence": 4,
            "required": 1,
            "validation_json": '{"max_accuracy_m": 50}',
        },
    ]

    for question_data in questions:
        option_rows = question_data.pop("options", [])
        question = _ensure_by_field(
            "FP Question",
            "question_code",
            question_data["question_code"],
            {"questionnaire": questionnaire.name, "active": 1, **question_data},
        )
        for sequence, (option_code, label) in enumerate(option_rows, start=1):
            if not frappe.db.exists("FP Question Option", {"question": question.name, "option_code": option_code}):
                frappe.get_doc(
                    {
                        "doctype": "FP Question Option",
                        "question": question.name,
                        "option_code": option_code,
                        "label": label,
                        "sequence": sequence,
                        "active": 1,
                    }
                ).insert(ignore_permissions=True)


def _ensure_doc(doctype, name, values):
    if frappe.db.exists(doctype, name):
        return frappe.get_doc(doctype, name)
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc


def _ensure_by_field(doctype, fieldname, value, values):
    existing = frappe.db.exists(doctype, {fieldname: value})
    if existing:
        return frappe.get_doc(doctype, existing)
    doc = frappe.get_doc({"doctype": doctype, **values})
    doc.insert(ignore_permissions=True)
    return doc

