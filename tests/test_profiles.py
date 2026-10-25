import json
from datetime import datetime, timedelta

from jarvis import config
from jarvis.brain import Brain
from jarvis.reminders import ReminderScheduler
from jarvis.tools import Tools

from .helpers import ToolsTestCase
from .test_multistep import ScriptedClaude, reply, text, tool


class ProfileTests(ToolsTestCase):
    cfg = {"user_name": "Quincy", "home_city": "Baton Rouge"}

    def test_main_profile_uses_settings(self):
        self.assertEqual(json.loads(self.call("list_profiles")), [{"name": "Quincy", "active": True}])
        self.assertEqual(self.tools.effective_cfg()["user_name"], "Quincy")

    def test_create_switches_and_overrides_name_and_city(self):
        self.assertIn("Created a profile for Marcus", self.call("create_profile", name="Marcus", home_city="Austin"))
        cfg = self.tools.effective_cfg()
        self.assertEqual((cfg["user_name"], cfg["home_city"]), ("Marcus", "Austin"))
        self.assertEqual(self.tools.cfg["active_profile"], "marcus")
        self.assertIn("already has a profile", self.call("create_profile", name="marcus"))

    def test_switch_by_spoken_name(self):
        self.call("create_profile", name="Marcus")
        self.assertIn("Switched to Quincy", self.call("switch_profile", name="quincy"))  # main by name
        self.assertIn("Switched to Marcus", self.call("switch_profile", name="MARCUS"))
        self.assertIn("already active", self.call("switch_profile", name="Marcus"))
        self.assertIn("no profile called Ana", self.call("switch_profile", name="Ana"))

    def test_notes_memories_and_reminders_are_per_person(self):
        when = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        self.call("save_note", text="Quincy's note")
        self.call("remember", text="Quincy likes jazz")
        self.call("set_reminder", text="Quincy's reminder", when=when)
        self.call("create_profile", name="Marcus")
        self.assertEqual(self.call("read_notes"), "No notes saved.")
        self.assertEqual(self.tools.memory_summary(), [])
        self.assertEqual(self.call("list_reminders"), "No upcoming reminders.")
        self.tools.confirm = lambda q, d, pin=False: True
        self.call("clear_notes")  # Marcus clearing his notes...
        self.call("switch_profile", name="Quincy")
        self.assertIn("Quincy's note", self.call("read_notes"))  # ...leaves Quincy's alone

    def test_switch_is_saved_through_callback(self):
        saved = []
        self.tools.on_profile_switch = saved.append
        self.call("create_profile", name="Marcus")
        self.assertEqual(saved, ["marcus"])

    def test_active_profile_restored_or_falls_back(self):
        self.call("create_profile", name="Marcus")
        self.assertEqual(Tools(store=self.store, cfg={"active_profile": "marcus"}).profile, "marcus")
        self.assertEqual(Tools(store=self.store, cfg={"active_profile": "deleted"}).profile, "default")

    def test_weather_uses_the_active_persons_home_city(self):
        self.call("create_profile", name="Marcus", home_city="Austin")
        self.tools.cfg["location_mode"] = "home"
        self.assertEqual(self.tools.locator.current().name, "Austin")
        self.call("switch_profile", name="Quincy")
        self.assertEqual(self.tools.locator.current().name, "Baton Rouge")

    def test_conversation_resets_when_the_person_changes(self):
        self.call("create_profile", name="Marcus")
        self.call("switch_profile", name="Quincy")
        b = Brain({"api_key": "test", "model": "claude-haiku-5-5", "web_search": False}, self.tools)
        b.client = ScriptedClaude(reply(text("Hi Quincy.")),
                                  reply(tool("switch_profile", "t1", name="Marcus"), stop="tool_use"),
                                  reply(text("Hello Marcus.")))
        b.ask("hi")
        self.assertEqual(len(b.history), 2)
        b.ask("this is Marcus")
        self.assertEqual(b.history, [])  # Marcus can't see Quincy's chat

    def test_reminder_announcements_say_whose_it_is(self):
        fired = []
        self.call("create_profile", name="Marcus")
        self.store.run("INSERT INTO reminders (profile, text, due, created) VALUES ('marcus', 'gym', ?, ?)",
                       ((datetime.now() - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S"),) * 2)
        ReminderScheduler(self.store, lambda t, late, p: fired.append((t, p))).check_due()
        self.assertEqual(fired, [("gym", "marcus")])


class OldNotesImportTests(ToolsTestCase):
    def test_notes_json_is_imported_once(self):
        self.tools.store.run("DELETE FROM notes")
        config.NOTES_PATH.write_text(json.dumps([{"text": "old note", "saved": "2026-01-01 09:00"}]))
        tools = Tools(store=self.store)
        self.assertEqual(json.loads(tools.dispatch("read_notes", {})), [{"text": "old note", "saved": "2026-01-01 09:00"}])
        self.assertFalse(config.NOTES_PATH.exists())
        self.assertTrue(config.NOTES_PATH.with_name("notes.json.imported").exists())
        Tools(store=self.store)  # second start: nothing to import, no duplicates
        self.assertEqual(len(json.loads(tools.dispatch("read_notes", {}))), 1)
