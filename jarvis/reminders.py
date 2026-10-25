"""Reminders at an absolute date and time. Unlike timers they're saved in the database,
so they survive restarts; any that came due while Drexya was closed are announced
on the next launch.
"""
import threading
from datetime import datetime, timedelta

DUE_FORMAT = "%Y-%m-%d %H:%M:%S"
LATE_AFTER = timedelta(minutes=1)  # fired this long after the due time = missed while off

SCHEMAS = [
    {
        "name": "set_reminder",
        "description": "Set a reminder for a specific date and time. It's saved, so it still fires after a "
                       "restart. Work out relative phrases ('tomorrow at 9', 'Friday evening', 'in 3 hours') "
                       "from the current time in your instructions. Use this instead of set_timer for anything "
                       "with a date or time of day, or more than an hour away.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What to remind them about, e.g. 'call the dentist'."},
                "when": {"type": "string", "description": "Local date and time, 'YYYY-MM-DD HH:MM' (24-hour)."},
            },
            "required": ["text", "when"],
        },
    },
    {
        "name": "list_reminders",
        "description": "List upcoming reminders.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel an upcoming reminder by its id from list_reminders, or by words that identify it. "
                       "If several match, you get them back and should ask which one.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "query": {"type": "string"}},
        },
    },
]


def spoken_time(dt: datetime, now: datetime = None) -> str:
    """'today at 3:05 PM', 'tomorrow at 9:00 AM', 'Friday, October 31 at 7:30 PM'."""
    now = now or datetime.now()
    clock = dt.strftime("%I:%M %p").lstrip("0")
    days = (dt.date() - now.date()).days
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    return f"{dt.strftime('%A, %B')} {dt.day} at {clock}"


def parse_when(when: str) -> datetime:
    when = when.strip().replace("T", " ")
    try:
        return datetime.fromisoformat(when).replace(tzinfo=None, microsecond=0)
    except ValueError:
        raise ValueError(f"'{when}' isn't a date and time I understand; use YYYY-MM-DD HH:MM") from None


class ReminderScheduler:
    """Background thread that sleeps until the next pending reminder and fires it.
    on_due(text, late) runs on this thread; late=True if it came due while Drexya was off."""

    def __init__(self, store, on_due):
        self.store = store
        self.on_due = on_due
        self._wake = threading.Event()
        self._stopped = False

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def wake(self):
        """Call after adding or cancelling, so the next due time is recalculated."""
        self._wake.set()

    def stop(self):
        self._stopped = True
        self._wake.set()

    def check_due(self, now: datetime = None) -> list:
        """Fire every pending reminder that's due. Returns what fired (for tests)."""
        now = now or datetime.now()
        due = self.store.query(
            "SELECT id, text, due FROM reminders WHERE status = 'pending' AND due <= ? ORDER BY due",
            (now.strftime(DUE_FORMAT),))
        fired = []
        for r in due:
            # Mark first so a crash in on_due can't make it fire again on every launch
            if self.store.run("UPDATE reminders SET status = 'fired' WHERE id = ? AND status = 'pending'",
                              (r["id"],)):
                late = now - datetime.strptime(r["due"], DUE_FORMAT) > LATE_AFTER
                fired.append((r["text"], late))
                try:
                    self.on_due(r["text"], late)
                except Exception as e:
                    print(f"[reminders] announcing failed: {e}")
        return fired

    def seconds_until_next(self, now: datetime = None) -> float:
        now = now or datetime.now()
        row = self.store.query("SELECT MIN(due) AS due FROM reminders WHERE status = 'pending'")
        if not row or row[0]["due"] is None:
            return 3600.0
        delta = (datetime.strptime(row[0]["due"], DUE_FORMAT) - now).total_seconds()
        return max(0.0, delta)

    def _run(self):
        while not self._stopped:
            try:
                self.check_due()
                # Cap the sleep so clock changes (sleep/hibernate, DST) are caught within a minute
                wait = min(self.seconds_until_next(), 60.0)
            except Exception as e:
                print(f"[reminders] {e}")
                wait = 30.0
            self._wake.wait(wait)
            self._wake.clear()


class ReminderTools:
    """Mixin for Tools. Needs self.store, self.profile and self.reminder_scheduler (or None)."""

    def _reminders_changed(self):
        if self.reminder_scheduler:
            self.reminder_scheduler.wake()

    def _pending(self):
        return self.store.query(
            "SELECT id, text, due FROM reminders WHERE profile = ? AND status = 'pending' ORDER BY due",
            (self.profile,))

    def t_set_reminder(self, text: str, when: str):
        due = parse_when(when)
        now = datetime.now()
        if due < now - LATE_AFTER:
            return f"That time has already passed ({spoken_time(due, now)}). Ask the user for a future time."
        self.store.run(
            "INSERT INTO reminders (profile, text, due, created) VALUES (?, ?, ?, ?)",
            (self.profile, text.strip(), due.strftime(DUE_FORMAT), now.strftime(DUE_FORMAT)))
        self._reminders_changed()
        return f"Reminder set for {spoken_time(due, now)}."

    def t_list_reminders(self):
        rows = self._pending()
        if not rows:
            return "No upcoming reminders."
        now = datetime.now()
        return [{"id": r["id"], "text": r["text"],
                 "when": spoken_time(datetime.strptime(r["due"], DUE_FORMAT), now)} for r in rows]

    def t_cancel_reminder(self, id: int = None, query: str = ""):
        if id is not None:
            matches = [r for r in self._pending() if r["id"] == id]
        else:
            q = query.strip().lower()
            if not q:
                return "Tell me which reminder to cancel."
            matches = [r for r in self._pending() if q in r["text"].lower()]
        if not matches:
            return "I couldn't find an upcoming reminder like that."
        if len(matches) > 1:
            return {"several_match": matches, "note": "Ask the user which one, then cancel it by id."}
        self.store.run("UPDATE reminders SET status = 'cancelled' WHERE id = ?", (matches[0]["id"],))
        self._reminders_changed()
        return f"Cancelled: {matches[0]['text']}."
