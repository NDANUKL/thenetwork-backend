import importlib.util
import json
import re
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).parents[1]


class Record(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def set(self, key, value): self[key] = [Record(row) for row in value] if isinstance(value, list) else value
    def is_new(self): return not self.get('name')
    def get_doc_before_save(self): return None


class FakeSite:
    def __init__(self):
        self.rows = {}
        self.session = types.SimpleNamespace(user='reviewer')
        self.get_roles = lambda: ['Field Operations Coordinator']
        self.db = types.SimpleNamespace(exists=self.exists, get_value=self.value)
        self.utils = types.SimpleNamespace(now_datetime=lambda: '2026-10-20 09:00:00')
    def throw(self, message): raise ValueError(message)
    def matching(self, dt, filters=None):
        rows = [row for (kind, name), row in self.rows.items() if kind == dt]
        if isinstance(filters, str): return [row for row in rows if row.name == filters]
        return [row for row in rows if all((row.get(k) in (None,'') if v == ['is','not set'] else row.get(k) == v) for k, v in (filters or {}).items())]
    def exists(self, dt, filters):
        rows = self.matching(dt, filters)
        return rows[0].name if rows else None
    def value(self, dt, filters, field, **kwargs):
        rows = self.matching(dt, filters)
        rows.sort(key=lambda row: row.get('version') or 0, reverse=True)
        return (Record({key:rows[0].get(key) for key in field}) if isinstance(field,list) else rows[0].get(field)) if rows else None
    def get_all(self, dt, filters=None, pluck=None, **kwargs):
        rows = self.matching(dt, filters)
        return [row.get(pluck) for row in rows] if pluck else rows
    def get_doc(self, dt, name=None):
        if isinstance(dt, str): return self.rows[(dt, name)]
        doc = Record(dt)
        def save(**kwargs):
            self.rows[(doc.doctype, doc.name)] = doc
            return doc
        def insert(**kwargs):
            doc.name = kwargs.get('set_name') or str(len(self.rows)+1)
            return save()
        doc.save, doc.insert = save, insert
        return doc




if __name__ == '__main__': unittest.main()
