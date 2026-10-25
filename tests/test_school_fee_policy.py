import ast
import json
import re
import unittest
from pathlib import Path
from fieldpulse.school_fees import apply_policy

ROOT = Path(__file__).parents[1]

class SchoolFeePolicyTests(unittest.TestCase):
    def test_all_catalogues_use_new_fee_versions_without_mutating_sources(self):
        for filename in ['scout-questionnaires.json', 'scout-questionnaires-v2.json', 'scout-questionnaires-v3.json']:
            original = json.loads((ROOT / 'fieldpulse/configuration' / filename).read_text(encoding='utf-8'))
            updated = apply_policy(original)
            fee = next(s for s in updated['services'] if s['service_code'] == 'university_fees')
            self.assertEqual(fee['title'], 'School fee payment confirmation')
            self.assertEqual(sum(service['service_code'] == 'university_fees' for service in updated['services']), 1)
            self.assertNotIn('University fee payment confirmation', [service['title'] for service in updated['services']])
            self.assertEqual(fee['questionnaire_version'], original['version'] + 3)
            self.assertIn('all ages', fee['description'])
            self.assertIn('no student contact', fee['description'])
            self.assertEqual(next(s for s in original['services'] if s['service_code'] == 'university_fees')['title'], 'University fee payment confirmation')
            self.assertEqual([s for s in original['services'] if s['service_code'] != 'university_fees'], [s for s in updated['services'] if s['service_code'] != 'university_fees'])

    def test_selection_supports_all_ages_and_preserves_other_restrictions(self):
        tree = ast.parse((ROOT / 'fieldpulse/scout_templates.py').read_text(encoding='utf-8'))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'infer_service')
        namespace = {'re': re}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<infer_service>', 'exec'), namespace)
        infer = namespace['infer_service']
        for text in ['Confirm school fees paid for my 10-year-old child at primary school', 'Verify school fee payment receipt', 'Confirm university fees paid']:
            self.assertEqual(infer(text), 'university_fees')
        for text in ['School enrolment', 'School attendance', 'School fee payment and attendance', 'School fees and clinic visit']:
            self.assertIsNone(infer(text))

    def test_new_fee_template_installation_preserves_old_published_records_and_project_pin(self):
        import copy
        import importlib.util
        import sys
        from unittest.mock import patch
        from test_scout_templates import FakeSite, Record
        class Site(FakeSite):
            def matching(self, dt, filters=None):
                if isinstance(filters, dict) and isinstance(filters.get('version'), list):
                    filters = dict(filters)
                    operator, versions = filters.pop('version')
                    return [row for row in super().matching(dt, filters) if row.version in versions]
                return super().matching(dt, filters)
        site = Site()
        spec = importlib.util.spec_from_file_location('fee_templates_test', ROOT / 'fieldpulse/scout_templates.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'frappe': site}):
            spec.loader.exec_module(module)
        historical = json.loads((ROOT / 'fieldpulse/configuration/scout-questionnaires.json').read_text(encoding='utf-8'))
        with patch.object(module, 'catalogue', return_value=historical):
            module.install_templates()
        old = copy.deepcopy(dict(site.get_doc('FP Questionnaire', 'DD-university_fees-v1')))
        module.install_templates()
        module.install_templates()
        self.assertEqual(dict(site.get_doc('FP Questionnaire', 'DD-university_fees-v1')), old)
        self.assertEqual(site.get_doc('FP Questionnaire', 'DD-university_fees-v4').title, 'School fee payment confirmation')
        project = Record(doctype='Field Request', name='fee-project', project_title='Confirm primary school fees paid for my child', request_type='General Site Visit')
        module.prepare_project(project)
        self.assertEqual(project.scout_questionnaire, 'DD-university_fees-v4')
        project.scout_service = 'University fee payment confirmation'
        project.scout_questionnaire = 'DD-university_fees-v1'
        project.scout_checks = []
        module.prepare_project(project)
        self.assertEqual(project.scout_questionnaire, 'DD-university_fees-v1')
