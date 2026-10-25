import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

from jarvis import config, providers
from jarvis.providers.base import CalendarProvider, Event
from jarvis.providers.google import GoogleCalendar, event_from_google, load_credentials

from .helpers import ToolsTestCase


class FakeCalendar(CalendarProvider):
    def __init__(self, events=()):
        self.events = list(events)
        self.listed = None

    def list_events(self, start, end, limit=20):
        self.listed = (start, end)
        return [e for e in self.events if start <= e.start < end]

    def create_event(self, title, start, end, all_day=False, location="", description=""):
        e = Event(title, start, end, all_day, location)
        self.events.append(e)
        return e


class CalendarToolTests(ToolsTestCase):
    cfg = {"calendar_provider": "google"}

    def setUp(self):
        super().setUp()
        self.fake = FakeCalendar()
        self.tools._calendar_cache = ("google", self.fake)

    def test_tools_offered_when_provider_set(self):
        names = {s["name"] for s in self.tools.schemas()}
        self.assertTrue({"get_calendar_events", "create_calendar_event"} <= names)

    def test_create_timed_event_then_read_it(self):
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        reply = self.call("create_calendar_event", title="Dentist", start=f"{tomorrow} 14:30",
                          duration_minutes=45, location="Main St")
        self.assertIn("Added 'Dentist', tomorrow at 2:30 PM until 3:15 PM", reply)
        events = json.loads(self.call("get_calendar_events", start_date=tomorrow))
        self.assertEqual(events, [{"title": "Dentist", "when": "tomorrow at 2:30 PM until 3:15 PM",
                                   "location": "Main St"}])

    def test_create_all_day_event(self):
        day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertIn("all day tomorrow", self.call("create_calendar_event", title="Holiday", start=day))
        self.assertTrue(self.fake.events[0].all_day)

    def test_week_range(self):
        self.call("get_calendar_events", start_date="2026-11-02", days=7)
        start, end = self.fake.listed
        self.assertEqual((start, end), (datetime(2026, 11, 2), datetime(2026, 11, 9)))

    def test_today_only_looks_ahead(self):
        self.call("get_calendar_events")
        start, end = self.fake.listed
        self.assertLessEqual(abs((start - datetime.now()).total_seconds()), 60)
        self.assertEqual(end, datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))

    def test_empty_and_bad_date(self):
        self.assertIn("Nothing on the calendar", self.call("get_calendar_events"))
        self.assertIn("isn't a date", self.call("get_calendar_events", start_date="Friday"))


class CalendarOffTests(ToolsTestCase):
    def test_hidden_and_explains_when_off(self):
        self.assertNotIn("get_calendar_events", {s["name"] for s in self.tools.schemas()})
        self.assertIn("isn't set up", self.call("get_calendar_events"))

    def test_provider_registry(self):
        self.assertIsNone(providers.get_calendar({"calendar_provider": "none"}))
        self.assertEqual(providers.google_features({"calendar_provider": "google"}), ["calendar"])


class GoogleCalendarTests(unittest.TestCase):
    def test_parses_timed_and_all_day_events(self):
        tz = datetime.now().astimezone().tzinfo
        start = datetime(2026, 11, 2, 9, 0, tzinfo=tz)
        timed = event_from_google({"summary": "Standup", "location": "Zoom",
                                   "start": {"dateTime": start.isoformat()},
                                   "end": {"dateTime": (start + timedelta(minutes=15)).isoformat()}})
        self.assertEqual((timed.title, timed.start, timed.all_day), ("Standup", datetime(2026, 11, 2, 9, 0), False))
        all_day = event_from_google({"summary": "Holiday", "start": {"date": "2026-11-26"},
                                     "end": {"date": "2026-11-27"}})
        self.assertTrue(all_day.all_day)
        self.assertEqual(all_day.start, datetime(2026, 11, 26))

    def test_list_sends_local_range_and_skips_cancelled(self):
        svc = mock.MagicMock()
        svc.events().list().execute.return_value = {"items": [
            {"summary": "Keep", "start": {"date": "2026-11-02"}, "end": {"date": "2026-11-03"}},
            {"summary": "Gone", "status": "cancelled", "start": {"date": "2026-11-02"}},
        ]}
        events = GoogleCalendar(service=svc).list_events(datetime(2026, 11, 2), datetime(2026, 11, 3))
        self.assertEqual([e.title for e in events], ["Keep"])
        kwargs = svc.events().list.call_args.kwargs
        self.assertEqual(kwargs["calendarId"], "primary")
        self.assertTrue(kwargs["singleEvents"])
        self.assertTrue(kwargs["timeMin"].startswith("2026-11-02T00:00:00"))

    def test_create_builds_google_body(self):
        svc = mock.MagicMock()
        svc.events().insert().execute.return_value = {"summary": "Lunch", "start": {"date": "2026-11-02"},
                                                      "end": {"date": "2026-11-03"}}
        GoogleCalendar(service=svc).create_event("Lunch", datetime(2026, 11, 2), datetime(2026, 11, 2),
                                                 all_day=True, location="Cafe")
        body = svc.events().insert.call_args.kwargs["body"]
        self.assertEqual(body["start"], {"date": "2026-11-02"})
        self.assertEqual(body["end"], {"date": "2026-11-03"})  # exclusive end, fixed up
        self.assertEqual(body["location"], "Cafe")

    def test_not_connected_without_token(self):
        with mock.patch.object(config, "GOOGLE_TOKEN_PATH", config.APP_DIR / "no-such-token.json"):
            with self.assertRaises(providers.NotConnected):
                load_credentials(["calendar"])
