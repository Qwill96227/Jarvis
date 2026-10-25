import json
import threading
from datetime import datetime, timedelta

from jarvis.reminders import DUE_FORMAT, ReminderScheduler, spoken_time
from jarvis.storage import Store
from jarvis.tools import Tools

from .helpers import ToolsTestCase


def at(minutes_from_now: float) -> str:
    return (datetime.now() + timedelta(minutes=minutes_from_now)).strftime("%Y-%m-%d %H:%M")


class ReminderToolTests(ToolsTestCase):
    def test_set_and_list(self):
        self.assertIn("Reminder set for", self.call("set_reminder", text="call mom", when=at(90)))
        rows = json.loads(self.call("list_reminders"))
        self.assertEqual(rows[0]["text"], "call mom")

    def test_iso_t_separator_accepted(self):
        when = at(90).replace(" ", "T")
        self.assertIn("Reminder set", self.call("set_reminder", text="x", when=when))

    def test_past_time_rejected(self):
        self.assertIn("already passed", self.call("set_reminder", text="x", when=at(-30)))
        self.assertEqual(self.call("list_reminders"), "No upcoming reminders.")

    def test_bad_format_reported(self):
        self.assertIn("isn't a date and time", self.call("set_reminder", text="x", when="next tuesday"))

    def test_cancel_by_query_and_ambiguity(self):
        self.call("set_reminder", text="dentist appointment", when=at(60))
        self.call("set_reminder", text="dentist bill", when=at(120))
        self.assertIn("several_match", self.call("cancel_reminder", query="dentist"))
        self.assertIn("Cancelled", self.call("cancel_reminder", query="bill"))
        self.assertEqual(len(json.loads(self.call("list_reminders"))), 1)

    def test_cancel_unknown(self):
        self.assertIn("couldn't find", self.call("cancel_reminder", id=99))

    def test_reminders_persist_across_restarts(self):
        self.call("set_reminder", text="water plants", when=at(60))
        self.store.close()
        self.store = Store(self.tmp / "test.db")
        tools = Tools(store=self.store)
        self.assertEqual(json.loads(tools.dispatch("list_reminders", {}))[0]["text"], "water plants")


class SchedulerTests(ToolsTestCase):
    def setUp(self):
        super().setUp()
        self.fired = []
        self.scheduler = ReminderScheduler(self.store, lambda text, late: self.fired.append((text, late)))

    def add(self, text, due: datetime, status="pending"):
        self.store.run("INSERT INTO reminders (profile, text, due, status, created) VALUES ('default', ?, ?, ?, ?)",
                       (text, due.strftime(DUE_FORMAT), status, due.strftime(DUE_FORMAT)))

    def test_fires_due_once_and_not_future(self):
        now = datetime.now()
        self.add("due now", now - timedelta(seconds=5))
        self.add("later", now + timedelta(hours=1))
        self.scheduler.check_due(now)
        self.scheduler.check_due(now)  # already fired: no repeat
        self.assertEqual(self.fired, [("due now", False)])

    def test_missed_while_off_is_flagged_late(self):
        now = datetime.now()
        self.add("yesterday's", now - timedelta(days=1))
        self.scheduler.check_due(now)
        self.assertEqual(self.fired, [("yesterday's", True)])

    def test_cancelled_never_fires(self):
        now = datetime.now()
        self.add("cancelled", now - timedelta(seconds=5), status="cancelled")
        self.assertEqual(self.scheduler.check_due(now), [])

    def test_seconds_until_next(self):
        now = datetime.now().replace(microsecond=0)
        self.assertEqual(self.scheduler.seconds_until_next(now), 3600.0)  # nothing pending
        self.add("soon", now + timedelta(seconds=90))
        self.assertAlmostEqual(self.scheduler.seconds_until_next(now), 90, delta=1)

    def test_background_thread_fires_new_reminder(self):
        done = threading.Event()
        self.scheduler.on_due = lambda text, late: done.set()
        self.scheduler.start()
        self.add("soon", datetime.now() + timedelta(seconds=1))
        self.scheduler.wake()
        self.assertTrue(done.wait(5), "reminder didn't fire within 5 seconds")
        self.scheduler.stop()


class SpokenTimeTests(ToolsTestCase):
    def test_phrasing(self):
        now = datetime(2026, 10, 25, 12, 0)
        self.assertEqual(spoken_time(datetime(2026, 10, 25, 15, 5), now), "today at 3:05 PM")
        self.assertEqual(spoken_time(datetime(2026, 10, 26, 9, 0), now), "tomorrow at 9:00 AM")
        self.assertEqual(spoken_time(datetime(2026, 10, 31, 19, 30), now), "Saturday, October 31 at 7:30 PM")
