import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

class AdoptionTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).parents[1]/'fieldpulse/patches/v1_0/adopt_desk_alignment.py'
        spec=importlib.util.spec_from_file_location('adoption_test',path); self.m=importlib.util.module_from_spec(spec)
        self.api=types.ModuleType('frappe')
        self.api.conf=types.SimpleNamespace(get=lambda key: True)
        def throw(message): raise ValueError(message)
        self.api.throw=throw; self.api.get_all=Mock(return_value=[]); self.api.get_doc=Mock()
        self.api.db=types.SimpleNamespace(exists=Mock(return_value=False),delete=Mock(),set_value=Mock())
        self.api.clear_cache=Mock(); self.api.as_json=lambda obj:'backup'
        with patch.dict(sys.modules,{'frappe':self.api}): spec.loader.exec_module(self.m)
    def test_unapproved_handover_preserves_scripts(self):
        self.api.conf.get=lambda key: False
        with self.assertRaises(ValueError): self.m.execute()
        self.api.db.delete.assert_not_called()
        self.api.db.set_value.assert_not_called()
    def test_clean_site_no_customization_mutations(self):
        self.m.execute(); self.api.db.delete.assert_not_called(); self.api.db.set_value.assert_not_called()
    def test_incompatible_field_aborts_before_mutations(self):
        self.api.get_all.side_effect=lambda dt,filters,**kw:[types.SimpleNamespace(name='unexpected')] if filters['dt']=='Diaspora Request' else []
        self.api.get_doc.return_value=types.SimpleNamespace(fieldname='county',fieldtype='Link',name='unexpected')
        with self.assertRaises(ValueError): self.m.execute()
        self.api.db.delete.assert_not_called(); self.api.db.set_value.assert_not_called()
    def test_backup_before_metadata_only_removal(self):
        calls=[]
        custom=types.SimpleNamespace(fieldname='county',fieldtype='Small Text',name='Diaspora Request-county',as_dict=lambda:{'name':'Diaspora Request-county'})
        self.api.get_all.side_effect=lambda dt,filters,**kw:[types.SimpleNamespace(name=custom.name)] if filters['dt']=='Diaspora Request' else []
        backup=types.SimpleNamespace(insert=lambda **kw:calls.append('backup'))
        self.api.get_doc.side_effect=lambda dt,name=None:backup if isinstance(dt,dict) else custom
        self.api.db.delete.side_effect=lambda *a:calls.append(a)
        self.m.execute()
        self.assertEqual(calls,['backup',('Custom Field',{'name':custom.name})])
        self.api.db.set_value.assert_not_called()

if __name__=='__main__': unittest.main()
