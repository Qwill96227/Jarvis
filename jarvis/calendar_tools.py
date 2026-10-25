"""Calendar tools. They work with whichever CalendarProvider is selected in settings
(see providers/), so adding Outlook later won't change anything here."""
from datetime import datetime, timedelta

from . import providers
from .reminders import parse_when, spoken_time

SCHEMAS = [
    {
        "name": "get_calendar_events",
        "description": "Read the user's calendar for a day or a range of days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "First day, 'YYYY-MM-DD'. Defaults to today."},
                "days": {"type": "integer", "minimum": 1, "maximum": 14,
                         "description": "How many days to cover. 1 = just that day, 7 = a week."},
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Add an event to the user's calendar. Confirm the title and time back in a few words.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string",
                          "description": "'YYYY-MM-DD HH:MM' (24-hour, local), or 'YYYY-MM-DD' for an all-day event."},
                "duration_minutes": {"type": "integer", "minimum": 5,
                                     "description": "Defaults to 60. Ignored for all-day events."},
                "location": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["title", "start"],
        },
    },
]


def _spoken_event(e, now) -> dict:
    if e.all_day:
        day = spoken_time(e.start, now).split(" at ")[0]
        when = f"all day {day}"
    else:
        when = f"{spoken_time(e.start, now)} until {e.end.strftime('%I:%M %p').lstrip('0')}"
    item = {"title": e.title, "when": when}
    if e.location:
        item["location"] = e.location
    return item


class CalendarTools:
    """Mixin for Tools. Needs self.cfg."""

    _calendar_cache = None  # (provider setting, provider)

    def calendar(self):
        setting = self.cfg.get("calendar_provider", "none")
        if not self._calendar_cache or self._calendar_cache[0] != setting:
            self._calendar_cache = (setting, providers.get_calendar(self.cfg))
        provider = self._calendar_cache[1]
        if provider is None:
            raise providers.NotConnected("The calendar isn't set up. It can be turned on in settings.")
        return provider

    def t_get_calendar_events(self, start_date: str = "", days: int = 1):
        try:
            first = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now()
        except ValueError:
            return f"'{start_date}' isn't a date; use YYYY-MM-DD."
        start = first.replace(hour=0, minute=0, second=0, microsecond=0)
        if not start_date:
            start = datetime.now().replace(second=0, microsecond=0)  # today: only what's still ahead
        end = first.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=max(1, min(days, 14)))
        try:
            events = self.calendar().list_events(start, end)
        except providers.NotConnected as e:
            return str(e)
        if not events:
            return "Nothing on the calendar for that time."
        now = datetime.now()
        return [_spoken_event(e, now) for e in events]

    def t_create_calendar_event(self, title: str, start: str, duration_minutes: int = 60,
                                location: str = "", description: str = ""):
        all_day = len(start.strip()) == 10  # just a date
        begin = parse_when(start + (" 00:00" if all_day else ""))
        end = begin + (timedelta(days=1) if all_day else timedelta(minutes=duration_minutes))
        try:
            event = self.calendar().create_event(title, begin, end, all_day=all_day,
                                                 location=location, description=description)
        except providers.NotConnected as e:
            return str(e)
        return f"Added '{event.title}', {_spoken_event(event, datetime.now())['when']}."
