"""Calendar and email providers behind small interfaces (see base.py), so tools never talk
to Google directly. To add Outlook: write OutlookCalendar / OutlookMail classes with the
same methods and register them below.
"""
from .base import CalendarProvider, Event, NotConnected


def google_features(cfg: dict) -> list:
    """Google services switched on in settings. One sign-in asks for all of them."""
    features = []
    if cfg.get("calendar_provider") == "google":
        features.append("calendar")
    return features


def _google_calendar(cfg):
    from .google import GoogleCalendar
    return GoogleCalendar(google_features(cfg))


# setting value -> factory (imported lazily so unused providers cost nothing at startup)
CALENDAR_PROVIDERS = {
    "google": _google_calendar,
}


def get_calendar(cfg: dict):
    """The configured CalendarProvider, or None if calendar is switched off."""
    factory = CALENDAR_PROVIDERS.get(cfg.get("calendar_provider", "none"))
    return factory(cfg) if factory else None
