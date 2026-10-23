"""Customer statuses must describe assignment across the complete project plan."""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch
from tests.test_native_integration import load, fake_frappe


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


class CustomerStageTests(unittest.TestCase):
    def setUp(self):
        self.api = fake_frappe()
        ownership = types.SimpleNamespace(owned_api=lambda name: lambda fn: fn,
            owned_event=lambda name: lambda fn: fn)
        self.module = load("customer_stage_test", "fieldpulse/customer_requests.py", {
            "frappe": self.api, "fieldpulse.beta_access": types.SimpleNamespace(require_access=lambda name: None),
            "fieldpulse.native_ownership": ownership})

    def stage(self, statuses, structured=True, source_status="Assigned", issues=None):
        projects = [Row(project_id="a", project_number=1, status=statuses[0])]
        if len(statuses) > 1:
            projects.append(Row(project_id="b", project_number=2, status=statuses[1]))
        self.api.get_all.return_value = projects
        plan = {"projects": [{"id": "a", "number": 1}, {"id": "b", "number": 2}], "issues": issues or []}
        alignment = types.SimpleNamespace(project_plan=MagicMock(return_value=plan))
        with patch.dict(sys.modules, {"fieldpulse.project_alignment": alignment}):
            return self.module.customer_stage(Row(name="request-1", status=source_status,
                project_contract_version=1 if structured else None))

    def test_partial_assignment_includes_missing_and_unassigned_projects(self):
        for structured in (True, False):
            for statuses in (["Assigned"], ["Assigned", "Awaiting Assignment"], ["In Progress", "Awaiting Assignment"]):
                with self.subTest(structured=structured, statuses=statuses):
                    self.assertEqual(self.stage(statuses, structured), "Partially assigned")

    def test_all_projects_assigned(self):
        self.assertEqual(self.stage(["Assigned", "Assigned"]), "Fully assigned")

    def test_no_assignments(self):
        self.assertEqual(self.stage(["Awaiting Assignment", "Awaiting Assignment"]), "New")

    def test_progress_and_completion_require_coverage(self):
        self.assertEqual(self.stage(["Completed", "Assigned"]), "In Progress")
        self.assertEqual(self.stage(["Completed", "Completed"]), "Completed")
        self.assertEqual(self.stage(["Completed"], source_status="Completed"), "Partially assigned")

    def test_rejected_status_is_preserved(self):
        self.assertEqual(self.stage(["Assigned"], source_status="Rejected"), "Rejected")

    def test_invalid_plan_does_not_claim_full_assignment(self):
        self.assertEqual(self.stage(["Assigned", "Assigned"], issues=["Missing scope"]), "Partially assigned")
