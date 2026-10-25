from jarvis import config

from .helpers import ToolsTestCase


class IsolationTests(ToolsTestCase):
    """Guard against tests touching the real user's files again."""

    def test_user_files_are_redirected_to_temp(self):
        for path in (config.NOTES_PATH, config.GOOGLE_TOKEN_PATH, config.GOOGLE_CLIENT_PATH):
            self.assertTrue(str(path).startswith(str(self.tmp)), path)

    def test_notes_go_to_the_test_database(self):
        self.call("save_note", text="isolation check")
        self.assertEqual(self.store.query("SELECT text FROM notes"), [{"text": "isolation check"}])
