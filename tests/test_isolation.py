from jarvis import config

from .helpers import ToolsTestCase


class IsolationTests(ToolsTestCase):
    """Guard against tests touching the real user's files again."""

    def test_notes_go_to_a_temp_file(self):
        self.assertTrue(str(config.NOTES_PATH).startswith(str(self.tmp)))
        self.call("save_note", text="isolation check")
        self.assertTrue(config.NOTES_PATH.exists())
