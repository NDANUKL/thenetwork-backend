"""Native handover regressions: API parity, ownership and fail-closed migration."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]
SNAPSHOT = json.loads((ROOT / 'docs/production-snapshots/2026-10-16.json').read_text(encoding='utf-8'))
PLAN = json.loads((ROOT / 'fieldpulse/configuration/native-ownership.json').read_text(encoding='utf-8'))


def load(name, relative, modules):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


def fake_frappe():
    api = MagicMock()
    api.whitelist = lambda **kwargs: lambda function: function
    api.response = {}
    api.PermissionError = PermissionError
    def throw(message, error=ValueError):
        raise error(message)
    api.throw.side_effect = throw
    return api


class NativeSourceTests(unittest.TestCase):
    def test_registry_hashes_match_utf8_audited_script_content(self):
        # Windows locale decoding previously corrupted the hash for non-ASCII punctuation.
        for record in SNAPSHOT['records']:
            if record['doctype'] not in ('Server Script', 'Client Script'):
                continue
            group = 'server_scripts' if record['doctype'] == 'Server Script' else 'client_scripts'
            canonical = record['script'].replace('\r\n', '\n').strip()
            expected = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
            self.assertEqual(PLAN[group][record['name']]['sha256'], expected, record['name'])


    def test_project_adoption_does_not_recreate_standard_fields(self):
        source = (ROOT / 'fieldpulse/patches/v1_0/permanent_project_contract.py').read_text(encoding='utf-8')
        self.assertNotIn('create_custom_fields', source)
        schema = json.loads((ROOT / 'fieldpulse/fieldpulse/doctype/field_request/field_request.json').read_text(encoding='utf-8'))
        self.assertIn('requires_verified_location', {field['fieldname'] for field in schema['fields']})

    def test_every_audited_script_has_native_owner_or_explicit_one_off_disposition(self):
        scripts = [r for r in SNAPSHOT['records'] if r['doctype'] == 'Server Script']
        self.assertEqual({r['name'] for r in scripts}, set(PLAN['server_scripts']))
        excluded = []
        for record in scripts:
            spec = PLAN['server_scripts'][record['name']]
            if not spec['target']:
                excluded.append(record['name'])
                self.assertIn('never replay', spec['disposition'])
                continue
            module, function = spec['target'].rsplit('.', 1)
            tree = ast.parse((ROOT / (module.replace('.', '/') + '.py')).read_text(encoding='utf-8'))
            self.assertIn(function, [n.name for n in tree.body if isinstance(n, ast.FunctionDef)])
        self.assertEqual(excluded, ['DD Currency Amendment DD-2026-00028'])

    def test_native_doctypes_preserve_production_fields_and_permissions(self):
        custom_fields = [r for r in SNAPSHOT['records'] if r['doctype'] == 'Custom Field']
        for record in SNAPSHOT['records']:
            if record['doctype'] != 'DocType':
                continue
            schema = json.loads((ROOT / PLAN['doctypes'][record['name']]).read_text(encoding='utf-8'))
            self.assertEqual(schema['module'], 'FieldPulse')
            self.assertEqual(schema['custom'], 0)
            self.assertEqual(schema.get('permissions'), record.get('permissions'))
            actual = {f['fieldname']: f for f in schema['fields']}
            for field in record['fields'] + [r for r in custom_fields if r['dt'] == record['name']]:
                # Retired after handover: unused assignment metadata.
                if record['name'] == 'Field Task' and field['fieldname'] == 'responsibility':
                    self.assertNotIn('responsibility', actual)
                    continue
                self.assertEqual(actual[field['fieldname']]['fieldtype'], field['fieldtype'])
                self.assertEqual(actual[field['fieldname']].get('options'), field.get('options'))
            self.assertEqual(len(actual), len(schema['fields']))

    def test_only_enabled_live_desk_scripts_are_supplied_by_native_assets(self):
        for record in SNAPSHOT['records']:
            if record['doctype'] != 'Client Script':
                continue
            folder = record['dt'].lower().replace(' ', '_')
            suffix = '_list.js' if record.get('view') == 'List' else '.js'
            path = ROOT / 'fieldpulse/fieldpulse/doctype' / folder / (folder + suffix)
            content = path.read_text(encoding='utf-8') if path.exists() else ''
            if record.get('enabled') and record['name'] == 'DD Project Scout Assignment':
                # The native picker now shows identity/county; retain the original
                # assignment route and deposit enforcement without freezing its UI.
                self.assertIn('dd_assign_scouts_without_extra_columns', content)
                self.assertIn('fieldname: "scout_name"', content)
                self.assertIn('fieldname: "base_county"', content)
                self.assertIn('frappe.db.get_value("Scout Profile"', content)
            elif record.get('enabled'):
                self.assertIn('\n'.join(line.strip() for line in record['script'].splitlines() if line.strip()), '\n'.join(line.strip() for line in content.splitlines() if line.strip()))
            else:
                self.assertNotIn('// ' + record['name'] + '\n', content)
        assignment = (ROOT / 'fieldpulse/fieldpulse/doctype/field_request/field_request.js').read_text(encoding='utf-8')
        self.assertNotIn('fieldname: "responsibility"', assignment)
        self.assertNotIn('fieldname: "location"', assignment)


class ApiParityTests(unittest.TestCase):
    def module(self, api, name):
        ownership = types.ModuleType('fieldpulse.native_ownership')
        ownership.owned_event = lambda *names: lambda function: function
        ownership.owned_api = lambda *names: lambda function: function
        policy = load('test_policy', 'fieldpulse/beta_access.py', {'frappe': api})
        return load('test_native_' + name, 'fieldpulse/' + name + '.py', {'frappe': api, 'fieldpulse.native_ownership': ownership, 'fieldpulse.beta_access': policy})

    def test_registration_rejects_non_admin_before_reading_customer_records(self):
        api = fake_frappe()
        api.db.exists.return_value = False
        api.form_dict = {'email': 'customer@example.com', 'action': 'register'}
        with self.assertRaises(PermissionError):
            self.module(api, 'customer_accounts').registration()
        api.get_doc.assert_not_called()

    def test_guest_cannot_read_scout_teammates(self):
        api = fake_frappe()
        api.session.user = 'Guest'
        api.form_dict = {'task': 'someone-elses-task'}
        with self.assertRaises(PermissionError):
            self.module(api, 'scout_registration').task_team()
        api.get_all.assert_not_called()

    def test_customer_pagination_uses_five_and_preserves_filters(self):
        script = next(r['script'] for r in SNAPSHOT['records'] if r['name'] == 'DD Customer Request Records')
        for filter_name in ('all', 'active', 'action', 'disputable'):
            results = []
            calls = []
            for native in (False, True):
                api = fake_frappe()
                api.session.user = 'customer@example.com'
                api.db.get_value.side_effect = lambda dt, name, field: 'Website User' if field == 'user_type' else 0 if field == 'desk_access' else 1
                api.db.exists.return_value = 'account-1'
                api.get_doc.return_value = {'beta_access': ''}
                api.get_roles.return_value = ['DD Customer']
                api.get_all.side_effect = lambda dt, **kw: ['DD Customer'] if dt == 'Has Role' else []
                api.utils.cint = int
                api.form_dict = {'action': 'requests', 'filter': filter_name, 'page': '2', 'email': 'customer@example.com'}
                if native:
                    result = self.module(api, 'customer_requests').requests()
                else:
                    exec(compile(script, '<audited-production>', 'exec'), {'frappe': api, 'json': json})
                    result = api.response['message']
                results.append(result)
                calls.append(api.get_all.call_args)
            self.assertEqual(results[0], results[1])
            # The retired script used three; native listings now show five.
            legacy_size = 20 if filter_name == 'disputable' else 3
            self.assertEqual(calls[0].kwargs['limit_start'], legacy_size)
            self.assertEqual(calls[0].kwargs['limit_page_length'], legacy_size + 1)
            size = 20 if filter_name == 'disputable' else 5
            self.assertEqual(calls[1].kwargs['limit_start'], size)
            self.assertEqual(calls[1].kwargs['limit_page_length'], size + 1)


class OwnershipTests(unittest.TestCase):
    def test_event_dormant_until_approved_and_legacy_script_disabled(self):
        api = fake_frappe()
        module = load('ownership_test', 'fieldpulse/native_ownership.py', {'frappe': api})
        called = []
        function = module.owned_event('legacy')(lambda: called.append(True))
        api.conf.get.return_value = False
        function()
        api.db.exists.assert_not_called()
        api.conf.get.return_value = True
        api.db.exists.return_value = True
        function()
        self.assertEqual(called, [])
        api.db.exists.return_value = False
        function()
        self.assertEqual(called, [True])


class ApiTransitionTests(unittest.TestCase):
    def test_active_legacy_api_keeps_original_executor_and_payload(self):
        api = fake_frappe()
        api.db.exists.return_value = True
        api.conf.get.return_value = False
        api.response = {"message": {"from": "live-script"}}
        api.get_doc.return_value.execute_method.return_value = {}
        module = load('api_ownership_test', 'fieldpulse/native_ownership.py', {'frappe': api})
        native = MagicMock(return_value='native')
        result = module.owned_api('legacy')(native)()
        self.assertEqual(result, {"from": "live-script"})
        native.assert_not_called()
        api.get_doc.return_value.execute_method.assert_called_once()

    def test_disabled_legacy_api_requires_approval_then_calls_native(self):
        api = fake_frappe()
        api.db.exists.return_value = False
        api.conf.get.return_value = False
        module = load('api_ownership_native_test', 'fieldpulse/native_ownership.py', {'frappe': api})
        module.registry = lambda: {"server_scripts": {"legacy": {"enable_rate_limit": 0}}}
        native = MagicMock(return_value={"from": "native"})
        endpoint = module.owned_api('legacy')(native)
        with self.assertRaises(PermissionError):
            endpoint()
        native.assert_not_called()
        api.conf.get.return_value = True
        self.assertEqual(endpoint(), {"from": "native"})

    def test_mutation_proof_is_checked_before_payment_mutation(self):
        api = fake_frappe()
        api.form_dict = {"action": "checkout", "reference": "request", "payment": "payment"}
        ownership = types.ModuleType('fieldpulse.native_ownership')
        ownership.owned_api = lambda *names: lambda function: function
        payments = types.ModuleType('fieldpulse.payments')
        commerce = types.ModuleType('fieldpulse.commerce')
        for name in ('roles','csrf','mutation_proof','billing','accept_quote','checkout','refresh','register_ipn','withdraw_quote','ipn','download_quote'):
            setattr(payments, name, MagicMock())
        for name in ('disputes','create_dispute','report','download_report','update_settings','deletion_request'):
            setattr(commerce, name, MagicMock())
        payments.mutation_proof.side_effect = PermissionError('stale token')
        module = load('payment_dispatch_test', 'fieldpulse/customer_payments.py', {'frappe': api, 'fieldpulse.native_ownership': ownership, 'fieldpulse.payments': payments, 'fieldpulse.commerce': commerce})
        with self.assertRaises(PermissionError):
            module.dispatch()
        payments.checkout.assert_not_called()

    def test_approved_report_is_visible_without_balance_payment_check(self):
        api = fake_frappe()
        api.db.get_value.return_value = 'report'
        api.get_doc.return_value = types.SimpleNamespace(name='report',title='Complete approved report',approved_at='now')
        payments = types.ModuleType('fieldpulse.payments')
        payments._customer = MagicMock()
        payments._owned = MagicMock()
        payments._lock = MagicMock()
        utils = types.ModuleType('frappe.utils')
        utils.now_datetime = lambda: 'now'
        module = load('commerce_report_test', 'fieldpulse/commerce.py', {'frappe': api, 'frappe.utils': utils, 'fieldpulse.payments': payments})
        self.assertTrue(module.report('request')['report']['released'])
        payments._owned.assert_called_once_with('request')
        api.db.exists.assert_not_called()


class HandoverTests(unittest.TestCase):
    def module(self, api):
        ownership = types.ModuleType('fieldpulse.native_ownership')
        ownership.registry = lambda: PLAN
        return load('handover_test', 'fieldpulse/native_handover.py', {'frappe': api, 'fieldpulse.native_ownership': ownership})

    def test_unapproved_handover_never_writes_or_deletes(self):
        api = fake_frappe()
        api.conf.get.return_value = False
        module = self.module(api)
        for operation in (module.adopt_schema, module.retire_scripts):
            with self.assertRaisesRegex(ValueError, 'approval'):
                operation()
        api.db.set_value.assert_not_called()
        api.db.delete.assert_not_called()

    def test_changed_script_blocks_retirement_before_any_writes(self):
        api = fake_frappe()
        api.conf.get.return_value = True
        api.db.exists.return_value = True
        api.get_doc.return_value = types.SimpleNamespace(script_type='API', script='changed')
        module = self.module(api)
        spec = dict(PLAN['server_scripts']['DD Customer Registration Bridge'])
        spec['target'] = None
        module.registry = lambda: {'server_scripts': {'DD Customer Registration Bridge': spec}, 'client_scripts': {}}
        with self.assertRaisesRegex(ValueError, 'changed since'):
            module.retire_scripts()
        api.db.set_value.assert_not_called()
        api.db.delete.assert_not_called()

    def test_mismatch_error_reports_hashes_without_exposing_script_content(self):
        api = fake_frappe()
        api.conf.get.return_value = True
        api.db.exists.return_value = True
        script = "private_script_body = 123\r\n"
        api.get_doc.return_value = types.SimpleNamespace(script_type='API', script=script)
        module = self.module(api)
        expected = dict(PLAN['server_scripts']['DD Customer Registration Bridge'])
        expected['target'] = None
        module.registry = lambda: {'server_scripts': {'DD Customer Registration Bridge': expected}, 'client_scripts': {}}
        with self.assertRaises(ValueError) as error:
            module.retire_scripts()
        message = str(error.exception)
        self.assertIn('Expected SHA256=' + expected['sha256'], message)
        self.assertIn('actual SHA256=' + module._digest(script), message)
        self.assertIn('CR=1; LF=1', message)
        self.assertNotIn('private_script_body', message)
        api.db.set_value.assert_not_called()
        api.db.delete.assert_not_called()

    def test_all_definitions_validated_and_backed_up_before_active_states_change(self):
        api = fake_frappe()
        module = self.module(api)
        originals = [{'doctype': 'Server Script', 'name': 'server'}, {'doctype': 'Client Script', 'name': 'client'}]
        events = []
        module.preflight = lambda: events.append('preflight') or originals
        module._backup = lambda *args: events.append('backup')
        api.db.set_value.side_effect = lambda *args: events.append(args)
        module.retire_scripts()
        self.assertEqual(events, ['preflight', 'backup', ('Server Script', 'server', 'disabled', 1), ('Client Script', 'client', 'enabled', 0)])
        api.db.delete.assert_not_called()

    def test_retirement_stops_old_scheduler_job_and_preserves_rollback_definition(self):
        api = fake_frappe()
        module = self.module(api)
        module.preflight = lambda: [{"doctype":"Server Script", "name":"reconcile", "script_type":"Scheduler Event"}]
        api.get_all.return_value = [types.SimpleNamespace(name='old-job')]
        api.get_doc.return_value.as_dict.return_value = {"name":"old-job", "stopped":0}
        backups = []
        module._backup = lambda filename, value: backups.append(value)
        module.retire_scripts()
        self.assertEqual(backups[0]['scheduled_jobs'], [{"name":"old-job", "stopped":0}])
        api.db.set_value.assert_any_call('Scheduled Job Type', 'old-job', 'stopped', 1)

    def test_new_unaudited_active_script_blocks_retirement(self):
        api = fake_frappe()
        api.conf.get.return_value = True
        api.get_all.return_value = ['DD New Production Change']
        module = self.module(api)
        module.registry = lambda: {'server_scripts': {}, 'client_scripts': {}}
        with self.assertRaisesRegex(ValueError, 'Unaudited active'):
            module.retire_scripts()
        api.db.set_value.assert_not_called()


if __name__ == '__main__':
    unittest.main()
