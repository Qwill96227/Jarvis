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


@dataclass
class Message:
    id: str
    sender: str
    subject: str
    date: datetime
    snippet: str = ""
    unread: bool = False
    body: str = ""  # only filled by get_message


class EmailProvider(ABC):
    name = "email"

    @abstractmethod
    def list_messages(self, limit: int = 10, unread_only: bool = False, query: str = "") -> list:
        """Newest inbox messages first (sender, subject, date, snippet; no body)."""

    @abstractmethod
    def get_message(self, message_id: str) -> Message:
        """One message including its plain-text body."""

    @abstractmethod
    def unread_count(self) -> int:
        """Unread messages in the inbox."""

    @abstractmethod
    def send(self, to: str, subject: str, body: str) -> str:
        """Send a plain-text email from the user's account. Returns the sent message id."""


class CalendarProvider(ABC):
    name = "calendar"

    @abstractmethod
    def list_events(self, start: datetime, end: datetime, limit: int = 20) -> list:
        """Events overlapping [start, end), soonest first."""

    @abstractmethod
    def create_event(self, title: str, start: datetime, end: datetime, all_day: bool = False,
                     location: str = "", description: str = "") -> Event:
        """Add an event to the user's main calendar and return it."""
