"""Validate structured customer projects without reading display labels."""
import json

class ProjectContractError(ValueError):
    pass

REQUEST_TYPES = {"land_property_check": "Property Verification", "construction_progress": "Construction Progress", "business_asset_check": "Business / Merchant Verification", "custom_ground_verification": "General Site Visit"}

def structured_projects(raw, *, strict=False):
    try:
        details = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as error:
        raise ProjectContractError("Project details must be a JSON array.") from error
    if not isinstance(details, list):
        raise ProjectContractError("Project details must be a JSON array.")
    ids, numbers, projects = set(), set(), []
    for detail in details:
        if not isinstance(detail, dict):
            raise ProjectContractError("Each project must be an object.")
        number = detail.get("number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ProjectContractError("Each project needs a positive integer number.")
        project_id = detail.get("id") or (f"legacy-project-{number}" if not strict else None)
        if not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 80:
            raise ProjectContractError("Each project needs a valid stable ID.")
        if project_id in ids or number in numbers:
            raise ProjectContractError("Project IDs and numbers must be unique.")
        ids.add(project_id)
        numbers.add(number)
        eligibility = detail.get("eligibility", "supported" if not strict else None)
        if eligibility not in {"supported", "scope_confirmation", "unsupported", "overseas"}:
            raise ProjectContractError("Invalid project eligibility.")
        if eligibility in {"unsupported", "overseas"}:
            continue
        description = detail.get("scope") or detail.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ProjectContractError("Every eligible project needs its own scope.")
        tasks = detail.get("evidence_tasks", [] if not strict else None)
        if not isinstance(tasks, list) or any(not isinstance(t, str) or not t.strip() for t in tasks):
            raise ProjectContractError("Project evidence must be a list of tasks.")
        category = detail.get("service_category")
        if strict and category not in REQUEST_TYPES:
            raise ProjectContractError("Invalid project service category.")
        county = detail.get("county") or ""
        location = detail.get("location_details") or {}
        fact = location.get("county") or {}
        if not county and isinstance(fact, dict) and fact.get("status") == "known":
            county = fact.get("value") or ""
        if not isinstance(county, str):
            raise ProjectContractError("Project county must be text.")
        projects.append({"id": project_id, "number": number, "title": detail.get("description") or description, "description": description, "county": county, "evidence": tasks, "request_type": REQUEST_TYPES.get(category), "scope_status": eligibility, "review": int(not county or not tasks or eligibility == "scope_confirmation")})
    return sorted(projects, key=lambda project: project["number"])

def assert_project_coverage(projects, rows):
    expected = {project["id"] for project in projects}
    actual = [row.get("project_id") for row in rows]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ProjectContractError("Project conversion is incomplete or duplicated; no combined request was saved.")

def validate_site_membership(projects, sites):
    expected = {project["id"] for project in projects}
    covered = set()
    for site in sites:
        try:
            ids = json.loads(site.get("project_ids") or "null")
        except (TypeError, ValueError) as error:
            raise ProjectContractError("Invalid site project IDs.") from error
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids):
            raise ProjectContractError("Every location must identify its projects explicitly.")
        if len(ids) != len(set(ids)) or not set(ids).issubset(expected):
            raise ProjectContractError("A location references a duplicate or unknown project.")
        covered.update(ids)
    required = {project["id"] for project in projects if project["scope_status"] == "supported"}
    if not required.issubset(covered):
        raise ProjectContractError("A supported project is missing its submitted location.")
