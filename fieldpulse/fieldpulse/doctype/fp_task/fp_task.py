import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from fieldpulse.utils import haversine_distance_m

STATUS_SEQUENCE = ["Draft", "Assigned", "In Progress", "Submitted", "Approved"]
TERMINAL_FROM_ANY = {"Cancelled", "Rejected"}


class FPTask(Document):
    def validate(self):
        if self.consent_status in ("Pending", "Declined", "Revoked") and self.status == "Assigned":
            frappe.throw("A task cannot be assigned before consent is granted")
        self._validate_status_transition()

    def _validate_status_transition(self):
        if self.is_new():
            return
        old_status = frappe.db.get_value("FP Task", self.name, "status")
        if old_status == self.status or self.status in TERMINAL_FROM_ANY:
            return
        if old_status not in STATUS_SEQUENCE or self.status not in STATUS_SEQUENCE:
            return
        if STATUS_SEQUENCE.index(self.status) < STATUS_SEQUENCE.index(old_status):
            frappe.throw(f"Cannot move task status backwards from {old_status} to {self.status}")


@frappe.whitelist(methods=["POST"])
def bulk_assign_tasks(questionnaire, agents, locations, due_date=None, priority="Normal"):
    """Create one task per (agent, location) pair for the given
    published questionnaire."""
    if isinstance(agents, str):
        agents = frappe.parse_json(agents)
    if isinstance(locations, str):
        locations = frappe.parse_json(locations)

    q_version = frappe.db.get_value("FP Questionnaire", questionnaire, "version")
    created = []

    for agent in agents:
        for location in locations:
            task_code = f"TASK-{frappe.generate_hash(length=8).upper()}"
            doc = frappe.get_doc({
                "doctype": "FP Task",
                "task_code": task_code,
                "agent": agent,
                "location": location,
                "questionnaire": questionnaire,
                "questionnaire_version": q_version,
                "consent_status": "Not Required",  # placeholder; revisit with Isaac-scope decision
                "assignment_source": "Manual",
                "status": "Assigned",
                "priority": priority,
                "due_at": due_date,
                "assigned_at": now_datetime(),
                "server_updated_at": now_datetime(),
            })
            doc.insert(ignore_permissions=True)
            created.append(doc.name)

    frappe.db.commit()
    return {"created": created, "count": len(created)}


@frappe.whitelist(methods=["POST"])
def auto_assign_by_proximity(questionnaire, agent, due_date=None, priority="Normal"):
    """Assign every active Location within the agent's service radius.
    Substitutes for the internship plan's 'auto-assign by region' --
    this schema uses GPS + service_radius_km instead of a named region."""
    agent_doc = frappe.get_doc("FP Agent", agent)
    if not (agent_doc.service_latitude and agent_doc.service_longitude and agent_doc.service_radius_km):
        frappe.throw("Agent is missing service location or service radius")

    candidates = frappe.get_all(
        "FP Location", filters={"status": "Active"}, fields=["name", "latitude", "longitude"]
    )
    in_range = [
        loc["name"] for loc in candidates
        if loc["latitude"] and loc["longitude"]
        and haversine_distance_m(
            agent_doc.service_latitude, agent_doc.service_longitude,
            loc["latitude"], loc["longitude"],
        ) / 1000 <= agent_doc.service_radius_km
    ]

    if not in_range:
        return {"created": [], "count": 0}

    return bulk_assign_tasks(questionnaire, [agent], in_range, due_date, priority)
