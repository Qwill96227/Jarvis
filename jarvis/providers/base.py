"""Provider interfaces. Times are local, timezone-naive datetimes throughout; each
provider converts to and from its service's format."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class NotConnected(Exception):
    """The account hasn't been connected yet (no sign-in). The message says how to fix it."""


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: str = ""


class CalendarProvider(ABC):
    name = "calendar"

    @abstractmethod
    def list_events(self, start: datetime, end: datetime, limit: int = 20) -> list:
        """Events overlapping [start, end), soonest first."""

    @abstractmethod
    def create_event(self, title: str, start: datetime, end: datetime, all_day: bool = False,
                     location: str = "", description: str = "") -> Event:
        """Add an event to the user's main calendar and return it."""
