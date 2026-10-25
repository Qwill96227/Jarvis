import json

from jarvis.brain import system_prompt
from jarvis.storage import Store
from jarvis.tools import Tools

from .helpers import ToolsTestCase


class MemoryTests(ToolsTestCase):
    def test_remember_and_recall(self):
        self.assertIn("remember", self.call("remember", text="Prefers Celsius", category="preference"))
        rows = json.loads(self.call("recall", query="celsius"))
        self.assertEqual(rows[0]["text"], "Prefers Celsius")
        self.assertEqual(rows[0]["category"], "preference")

    def test_duplicate_is_not_saved_twice(self):
        self.call("remember", text="Has a dog named Rex")
        self.assertIn("already", self.call("remember", text="has a dog named rex"))
        self.assertEqual(len(json.loads(self.call("recall"))), 1)

    def test_recall_falls_back_to_individual_words(self):
        self.call("remember", text="Sister is called Ana")
        rows = json.loads(self.call("recall", query="what is my sister's name"))
        self.assertEqual(rows[0]["text"], "Sister is called Ana")

    def test_recall_nothing(self):
        self.assertIn("don't have anything", self.call("recall"))
        self.assertIn("Nothing remembered", self.call("recall", query="cats"))

    def test_forget_by_query_single_match(self):
        self.call("remember", text="Works night shifts")
        self.assertIn("Forgotten", self.call("forget", query="night shifts"))
        self.assertIn("don't have anything", self.call("recall"))

    def test_forget_ambiguous_asks_which(self):
        self.call("remember", text="Likes jazz")
        self.call("remember", text="Likes jazz festivals")
        result = json.loads(self.call("forget", query="jazz"))
        self.assertEqual(len(result["several_match"]), 2)
        self.assertEqual(len(json.loads(self.call("recall"))), 2)  # nothing deleted

    def test_forget_by_id(self):
        self.call("remember", text="Allergic to peanuts")
        mid = json.loads(self.call("recall"))[0]["id"]
        self.assertEqual(self.call("forget", id=mid), "Forgotten.")
        self.assertIn("no memory", self.call("forget", id=mid))

    def test_memories_persist_across_restarts(self):
        self.call("remember", text="Birthday is March 3")
        self.store.close()
        self.store = Store(self.tmp / "test.db")  # tearDown closes this one
        tools = Tools(store=self.store)
        self.assertEqual(tools.memory_summary(), ["Birthday is March 3"])

    def test_profiles_are_separate(self):
        self.call("remember", text="Prefers tea")
        self.tools.profile = "marcus"
        self.assertIn("don't have anything", self.call("recall"))

    def test_system_prompt_includes_memories(self):
        self.call("remember", text="Prefers Celsius")
        prompt = system_prompt({"user_name": "Quincy"}, self.tools.memory_summary())
        self.assertIn("- Prefers Celsius", prompt)


class MemoryDisabledTests(ToolsTestCase):
    cfg = {"memory_enabled": False}

    def test_tools_and_prompt_hidden_when_disabled(self):
        names = {s["name"] for s in self.tools.schemas()}
        self.assertNotIn("remember", names)
        self.assertEqual(self.tools.memory_summary(), [])
        self.assertNotIn("Memory:", system_prompt(self.cfg))
