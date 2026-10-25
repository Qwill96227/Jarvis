"""Google sign-in (OAuth for an installed app), Google Calendar and Gmail.

Setup is one-time and documented in the README: create a Desktop OAuth client in Google
Cloud, save its JSON as %APPDATA%\\Jarvis\\google_client.json, then click Connect Google
in settings. The resulting token is saved to google_token.json and refreshed automatically.
"""
import base64
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime

from .. import config
from .base import CalendarProvider, EmailProvider, Event, Message, NotConnected

SCOPES = {
    "calendar": ["https://www.googleapis.com/auth/calendar.events"],
    "email": ["https://www.googleapis.com/auth/gmail.readonly",
              "https://www.googleapis.com/auth/gmail.send"],
}

SETUP_HINT = "Google isn't connected yet. Open settings and click Connect Google (setup steps are in the README)."


def _scopes_for(features) -> list:
    return sorted({s for f in features for s in SCOPES[f]})


def load_credentials(features):
    """Saved credentials covering every scope the features need, refreshed if expired.
    Raises NotConnected if the user hasn't signed in (or signed in with fewer scopes)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    scopes = _scopes_for(features)
    if not config.GOOGLE_TOKEN_PATH.exists():
        raise NotConnected(SETUP_HINT)
    creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN_PATH))
    if not set(scopes) <= set(creds.scopes or []):
        raise NotConnected("Google needs to be reconnected to allow this. Open settings and click Connect Google.")
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            config.GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise NotConnected(SETUP_HINT)
    return creds


def connect(features) -> str:
    """Interactive sign-in: opens the browser, waits for consent, saves the token.
    Blocking; run it on a background thread. Returns a status message."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not config.GOOGLE_CLIENT_PATH.exists():
        return (f"First save your Google OAuth client file as {config.GOOGLE_CLIENT_PATH} "
                "(see the README for how to create it).")
    flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CLIENT_PATH), _scopes_for(features))
    creds = flow.run_local_server(port=0, open_browser=True,
                                  success_message="Drexya is connected. You can close this tab.")
    config.GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return "Google connected."


def _service(api: str, version: str, features):
    from googleapiclient.discovery import build
    return build(api, version, credentials=load_credentials(features), cache_discovery=False)


def _local_tz():
    return datetime.now().astimezone().tzinfo


def _to_google_time(dt: datetime, all_day: bool) -> dict:
    if all_day:
        return {"date": dt.date().isoformat()}
    return {"dateTime": dt.replace(tzinfo=_local_tz()).isoformat()}


def _from_google_time(t: dict) -> tuple:
    """Google start/end dict -> (local naive datetime, all_day)."""
    if "date" in t:
        return datetime.combine(date.fromisoformat(t["date"]), datetime.min.time()), True
    dt = datetime.fromisoformat(t["dateTime"].replace("Z", "+00:00"))
    return dt.astimezone(_local_tz()).replace(tzinfo=None), False


def event_from_google(item: dict) -> Event:
    start, all_day = _from_google_time(item["start"])
    end, _ = _from_google_time(item.get("end", item["start"]))
    return Event(title=item.get("summary", "(no title)"), start=start, end=end,
                 all_day=all_day, location=item.get("location", ""))


class GoogleCalendar(CalendarProvider):
    name = "Google Calendar"

    def __init__(self, features=("calendar",), service=None):
        self.features = features  # every Google feature in use, so one sign-in covers them all
        self._svc = service       # injectable for tests

    @property
    def svc(self):
        if self._svc is None:
            self._svc = _service("calendar", "v3", self.features)
        return self._svc

    def list_events(self, start, end, limit=20):
        tz = _local_tz()
        resp = self.svc.events().list(
            calendarId="primary",
            timeMin=start.replace(tzinfo=tz).isoformat(),
            timeMax=end.replace(tzinfo=tz).isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=limit,
        ).execute()
        return [event_from_google(i) for i in resp.get("items", []) if i.get("status") != "cancelled"]

    def create_event(self, title, start, end, all_day=False, location="", description=""):
        if all_day and end.date() <= start.date():
            end = start + timedelta(days=1)  # Google's all-day end date is exclusive
        body = {"summary": title, "start": _to_google_time(start, all_day), "end": _to_google_time(end, all_day)}
        if location:
            body["location"] = location
        if description:
            body["description"] = description
        return event_from_google(self.svc.events().insert(calendarId="primary", body=body).execute())


# ---------------------------------------------------------------- Gmail
def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _plain_text(part: dict) -> str:
    """First text/plain body in a (possibly nested multipart) Gmail payload."""
    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
        return _decode(part["body"]["data"])
    for sub in part.get("parts", []) or []:
        text = _plain_text(sub)
        if text:
            return text
    return ""


def message_from_gmail(msg: dict, with_body: bool = False) -> Message:
    name, addr = parseaddr(_header(msg, "From"))
    try:
        when = parsedate_to_datetime(_header(msg, "Date")).astimezone().replace(tzinfo=None)
    except (TypeError, ValueError):
        when = datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000)
    return Message(
        id=msg["id"], sender=name or addr, subject=_header(msg, "Subject") or "(no subject)",
        date=when, snippet=msg.get("snippet", ""), unread="UNREAD" in msg.get("labelIds", []),
        body=_plain_text(msg.get("payload", {})) if with_body else "",
    )


class Gmail(EmailProvider):
    name = "Gmail"

    def __init__(self, features=("email",), service=None):
        self.features = features
        self._svc = service

    @property
    def svc(self):
        if self._svc is None:
            self._svc = _service("gmail", "v1", self.features)
        return self._svc

    def list_messages(self, limit=10, unread_only=False, query=""):
        q = " ".join(filter(None, ["in:inbox", "is:unread" if unread_only else "", query]))
        ids = self.svc.users().messages().list(userId="me", q=q, maxResults=limit).execute().get("messages", [])
        return [message_from_gmail(self.svc.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject", "Date"]).execute())
                for m in ids]

    def get_message(self, message_id):
        return message_from_gmail(
            self.svc.users().messages().get(userId="me", id=message_id, format="full").execute(), with_body=True)

    def unread_count(self):
        return self.svc.users().labels().get(userId="me", id="INBOX").execute().get("messagesUnread", 0)

    def send(self, to, subject, body):
        mime = MIMEText(body)
        mime["To"], mime["Subject"] = to, subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        return self.svc.users().messages().send(userId="me", body={"raw": raw}).execute()["id"]
