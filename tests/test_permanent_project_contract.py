import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch
from fieldpulse.project_contract import structured_projects, assert_project_coverage, validate_site_membership, ProjectContractError

class Doc(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def save(self, **kwargs): return self

def projects(count=3):
    return [{"id": f"stable-{number}", "number": number, "description": f"Changed display label {number}", "scope": f"Inspect project {number}", "county": ["Vihiga", "Kajiado", "Nairobi"][number-1], "service_category": "land_property_check", "eligibility": "supported", "evidence_tasks": [f"Photograph site {number}"]} for number in range(1, count+1)]

class ContractTests(unittest.TestCase):
    def test_three_project_identity_scope_evidence(self):
        actual = structured_projects(json.dumps(projects()), strict=True)
        self.assertEqual([p["id"] for p in actual], ["stable-1", "stable-2", "stable-3"])
        self.assertEqual(actual[1]["evidence"], ["Photograph site 2"])
        self.assertEqual(actual[1]["description"], "Inspect project 2")
    def test_display_wording_cannot_change_identity(self):
        details = projects()
        before = structured_projects(details, strict=True)
        for row in details: row["description"] = "Any wording ? any separator"
        after = structured_projects(details, strict=True)
        self.assertEqual([(p["id"], p["county"], p["evidence"]) for p in before], [(p["id"], p["county"], p["evidence"]) for p in after])
    def test_duplicate_missing_and_invalid_identity_rejected(self):
        for mutate in [lambda p: p[1].update(id=p[0]["id"]), lambda p: p[1].update(number=1), lambda p: p[1].pop("id"), lambda p: p[1].update(number=True)]:
            details=projects(); mutate(details)
            with self.assertRaises(ProjectContractError): structured_projects(details, strict=True)
    def test_unsupported_projects_do_not_create_field_work(self):
        details=projects(); details[1]["eligibility"]="unsupported"; details[2]["eligibility"]="overseas"
        self.assertEqual(len(structured_projects(details, strict=True)),1)
    def test_invalid_and_missing_evidence_cannot_fall_back_to_text(self):
        for value in ["legacy label", None, [None]]:
            details=projects(); details[0]["evidence_tasks"]=value
            with self.assertRaises(ProjectContractError): structured_projects(details, strict=True)
    def test_exact_coverage_rejects_combined_missing_and_duplicate_records(self):
        plan=structured_projects(projects(),strict=True)
        for ids in [[None], ["stable-1","stable-2"], ["stable-1","stable-1","stable-3"], ["stable-1","stable-2","stable-3","extra"]]:
            with self.assertRaises(ProjectContractError): assert_project_coverage(plan,[{"project_id":identity} for identity in ids])
        assert_project_coverage(plan,[{"project_id":p["id"]} for p in plan])
    def test_locations_are_bound_to_ids_including_shared_visits(self):
        plan=structured_projects(projects(),strict=True)
        validate_site_membership(plan,[{"project_ids":json.dumps(["stable-1","stable-2"])},{"project_ids":json.dumps(["stable-3"])}])
        for sites in [[],[{"project_ids":"[\"unknown\"]"}],[{"project_ids":"\"stable-1\""}],[{"project_ids":"[\"stable-1\",\"stable-1\"]"}]]:
            with self.assertRaises(ProjectContractError): validate_site_membership(plan,sites)

class ConversionTests(unittest.TestCase):
    def setUp(self):
        fake=types.ModuleType("frappe"); fake.whitelist=lambda **kw: lambda fn: fn
        spec=importlib.util.spec_from_file_location("conversion_test",Path(__file__).parents[1]/"fieldpulse/project_alignment.py")
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{"frappe":fake}): spec.loader.exec_module(self.module)
        def throw(message,*args): raise ProjectContractError(message)
        self.rows=[]
        def make_doc(value,*args):
            if isinstance(value,str): return next(row for row in self.rows if row.name==args[0])
            doc=Doc(value)
            def insert(**kw):
                doc.name=f"FR-{len(self.rows)+1}"; self.rows.append(doc); return doc
            doc.insert=insert;return doc
        self.module.frappe=types.SimpleNamespace(throw=throw,get_doc=make_doc,get_all=lambda *args,**kw:self.rows,db=types.SimpleNamespace(sql=Mock()))
        self.source=Doc(name="DD-test")
        self.plan={"projects":structured_projects(projects(),strict=True),"issues":[],"deadline":None}
        self.module.project_plan=lambda source:self.plan
    def test_retries_reuse_exact_project_records(self):
        self.module.ensure_field_requests(self.source)
        self.module.ensure_field_requests(self.source)
        self.assertEqual(len(self.rows),3)
        self.assertEqual([row.project_key for row in self.rows],["DD-test:stable-1","DD-test:stable-2","DD-test:stable-3"])
        self.assertEqual(self.module.frappe.db.sql.call_count,2)
    def test_conversion_failure_is_not_swallowed(self):
        self.module.frappe.get_doc=Mock(side_effect=RuntimeError("Database insert failed"))
        with self.assertRaisesRegex(RuntimeError,"insert failed"): self.module.ensure_field_requests(self.source)
    def test_duplicate_existing_records_stop_conversion(self):
        self.rows=[Doc(name="FR-1",project_id="stable-1",project_number=1),Doc(name="FR-2",project_id="stable-1",project_number=1)]
        with self.assertRaisesRegex(ProjectContractError,"Duplicate Field"): self.module.ensure_field_requests(self.source)

if __name__ == "__main__": unittest.main()
