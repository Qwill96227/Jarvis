"""Shared test setup: a Tools instance backed by a throwaway database."""
import tempfile
import unittest
from pathlib import Path

from jarvis.storage import Store
from jarvis.tools import Tools


class ToolsTestCase(unittest.TestCase):
    cfg = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = Store(self.tmp / "test.db")
        self.tools = Tools(store=self.store, cfg=dict(self.cfg))

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def call(self, name, **args):
        return self.tools.dispatch(name, args)
