import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]

class ConfigurationTests(unittest.TestCase):
    def test_audit_manifest_covers_managed_configuration_without_duplicates(self):
        records=json.loads((ROOT/'fieldpulse/configuration/production-configuration.json').read_text())['records']
        identities=[(row['doctype'],row['name']) for row in records]
        self.assertEqual(len(identities),len(set(identities)))
        self.assertTrue({'Role','DocType','Custom Field','Custom DocPerm','Property Setter','Server Script','Client Script','Print Format'}.issubset({row['doctype'] for row in records}))
        self.assertTrue(any(row['name']=='Diaspora Desk Quotation' and row['doctype']=='Print Format' for row in records))
        self.assertTrue(any(row['name']=='DD Customer Request Records' for row in records))
        self.assertTrue(all('owner' not in row and 'modified_by' not in row for row in records))

    def test_adoption_keeps_native_scripts_disabled_and_skips_standard_identity_fields(self):
        inserted=[]
        class Doc(dict):
            def insert(self,**kwargs): inserted.append(dict(self));return self
        fake=types.ModuleType('frappe')
        fake.db=types.SimpleNamespace(exists=lambda *args:False,get_value=lambda *args:None)
        fake.clear_cache=lambda:None
        def get_doc(value,name=None):
            if isinstance(value,dict):return Doc(value)
            identity='project_id' if name=='Field Request' else 'project_contract_version' if name=='Diaspora Request' else None
            return types.SimpleNamespace(fields=[types.SimpleNamespace(fieldname=identity)] if identity else [])
        fake.get_doc=get_doc
        spec=importlib.util.spec_from_file_location('configuration_test',ROOT/'fieldpulse/production_configuration.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'frappe':fake}):spec.loader.exec_module(module)
        module.apply_configuration()
        installed={(row['doctype'],row['name']) for row in inserted}
        self.assertFalse(any(('Server Script',name) in installed for name in module.NATIVE_EVENTS))
        self.assertNotIn(('Custom Field','Field Request-project_id'),installed)
        self.assertNotIn(('Custom Field','Diaspora Request-project_contract_version'),installed)
        self.assertFalse(any(dt in {'Server Script','Client Script','DocType','Print Format'} for dt,name in installed))
        self.assertNotIn(('Print Format','Diaspora Desk Quotation'),installed)
        self.assertEqual(sum(row['doctype']=='Custom DocPerm' for row in inserted),4)

if __name__=='__main__':unittest.main()
