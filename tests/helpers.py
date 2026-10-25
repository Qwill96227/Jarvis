"""Shared test setup: a Tools instance backed by throwaway files.

Every path a tool can write under %APPDATA%\\Jarvis must be redirected here, or tests
touch the real user's data (an early version cleared the real notes.json)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jarvis import config
from jarvis.storage import Store
from jarvis.tools import Tools


class ToolsTestCase(unittest.TestCase):
    cfg = {}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        for name in ("NOTES_PATH", "GOOGLE_TOKEN_PATH", "GOOGLE_CLIENT_PATH"):
            patcher = mock.patch.object(config, name, self.tmp / getattr(config, name).name)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.store = Store(self.tmp / "test.db")
        self.tools = Tools(store=self.store, cfg=dict(self.cfg))

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def call(self, _tool, **args):
        return self.tools.dispatch(_tool, args)
