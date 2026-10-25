import json
import unittest
from datetime import datetime, timedelta

from jarvis import safety

from .helpers import ToolsTestCase


class PinTests(unittest.TestCase):
    def test_hash_and_verify(self):
        stored = safety.hash_pin("4821")
        self.assertNotIn("4821", stored)
        self.assertTrue(safety.verify_pin(stored, "4821"))
        self.assertFalse(safety.verify_pin(stored, "4822"))
        self.assertFalse(safety.verify_pin(stored, ""))
        self.assertNotEqual(stored, safety.hash_pin("4821"))  # salted

    def test_bad_stored_value(self):
        self.assertFalse(safety.verify_pin("", "1234"))
        self.assertFalse(safety.verify_pin("garbage", "1234"))

    def test_valid_pins(self):
        self.assertTrue(safety.valid_pin("1234"))
        self.assertTrue(safety.valid_pin("12345678"))
        for bad in ("123", "123456789", "12a4", "", None):
            self.assertFalse(safety.valid_pin(bad), bad)


class PinGateTests(ToolsTestCase):
    def setUp(self):
        super().setUp()
        self.asked = []
        self.answer = True
        self.tools.confirm = lambda q, d, pin=False: self.asked.append((q, pin)) or self.answer
        self.call("save_note", text="keep me")

    def test_pin_required_once_set(self):
        self.call("clear_notes")
        self.assertEqual(self.asked[-1], ("Delete all your notes?", False))  # no PIN set yet: plain confirm
        self.tools.cfg["pin_hash"] = safety.hash_pin("1234")
        self.call("save_note", text="again")
        self.call("clear_notes")
        self.assertEqual(self.asked[-1], ("Delete all your notes?", True))

    def test_wrong_pin_blocks_and_is_logged(self):
        self.tools.cfg["pin_hash"] = safety.hash_pin("1234")
        self.answer = "pin_failed"
        self.assertIn("PIN was wrong", self.call("clear_notes"))
        self.assertIn("keep me", self.call("read_notes"))
        self.assertEqual(self.store.query("SELECT outcome FROM audit WHERE tool = 'clear_notes'"),
                         [{"outcome": "pin_failed"}])

    def test_pin_tools_also_need_confirmation(self):
        self.tools.cfg.update({"pin_hash": safety.hash_pin("1234"), "confirm_tools": [], "pin_tools": ["save_note"]})
        self.call("save_note", text="x")
        self.assertEqual(self.asked[-1][1], True)

    def test_only_true_counts_as_yes(self):
        for weird in (None, "yes", 1):
            self.answer = weird
            self.assertIn("did not confirm", self.call("clear_notes"))


class AuditTests(ToolsTestCase):
    def rows(self):
        return self.store.query("SELECT tool, args, outcome, detail FROM audit ORDER BY id")

    def test_every_call_is_logged_with_outcome(self):
        self.call("save_note", text="buy milk")
        self.call("no_such_tool")
        self.call("clear_notes")  # no confirm hook -> declined
        self.assertEqual([(r["tool"], r["outcome"]) for r in self.rows()],
                         [("save_note", "ok"), ("no_such_tool", "error"), ("clear_notes", "declined")])
        self.assertEqual(json.loads(self.rows()[0]["args"]), {"text": "buy milk"})

    def test_secrets_masked_and_long_text_shortened(self):
        safety.log_call(self.store, "default", "x", {"ha_token": "abc", "body": "y" * 500}, "ok")
        args = json.loads(self.rows()[0]["args"])
        self.assertEqual(args["ha_token"], "***")
        self.assertLessEqual(len(args["body"]), 120)

    def test_old_entries_pruned(self):
        old = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
        self.store.run("INSERT INTO audit (ts, profile, tool, args, outcome) VALUES (?, 'default', 'old', '{}', 'ok')",
                       (old,))
        self.call("get_datetime")
        safety.prune(self.store, 90)
        self.assertEqual([r["tool"] for r in self.rows()], ["get_datetime"])

    def test_recent_activity_is_per_person_and_skips_itself(self):
        self.call("save_note", text="mine")
        self.call("create_profile", name="Marcus")
        self.call("get_datetime")
        activity = json.loads(self.call("recent_activity"))
        self.assertEqual([a["action"] for a in activity], ["get datetime"])  # Marcus only; no create (logged as Quincy)
        self.call("switch_profile", name="Main")
        actions = [a["action"] for a in json.loads(self.call("recent_activity"))]
        self.assertIn("save note", actions)
        self.assertNotIn("get datetime", actions)


class AuditOffTests(ToolsTestCase):
    cfg = {"audit_enabled": False}

    def test_nothing_logged(self):
        self.call("get_datetime")
        self.assertEqual(self.store.query("SELECT * FROM audit"), [])
        self.assertNotIn("recent_activity", {s["name"] for s in self.tools.schemas()})
