"""Local tools Drexya can call. Each tool = a JSON schema + a method named t_<tool_name>.

To add a tool: add its schema to TOOL_SCHEMAS (or to a feature module's SCHEMAS) and a
t_<tool_name> method on Tools (or on that module's mixin). dispatch() finds it by name.
Claude decides when to call it based on the description.

Bigger features live in their own modules (memory.py, ...). Each one has a SCHEMAS list
and a mixin class with its t_ methods, which Tools inherits.
"""
import json
import os
import shutil
import subprocess
import threading
import time
import webbrowser
from datetime import datetime

import requests

from . import (calendar_tools, config, email_tools, home_assistant, location, memory, profiles, reminders,
               safety, system_tools)
from .storage import Store

try:
    import psutil
except ImportError:  # optional
    psutil = None

try:
    import keyboard  # media keys + global hotkey (Windows)
except Exception:
    keyboard = None


TOOL_SCHEMAS = [
    {
        "name": "get_datetime",
        "description": "Get the current local date and time.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_weather",
        "description": "Current conditions and a 3-day forecast. Leave location empty for wherever the "
                       "user is right now (detected automatically).",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string",
                                        "description": "City name, e.g. 'Baton Rouge'. Omit for the current location."}},
        },
    },
    {
        "name": "set_timer",
        "description": "Start a countdown timer. Drexya announces it out loud when it finishes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "minimum": 1},
                "label": {"type": "string", "description": "What the timer is for, e.g. 'pizza'"},
            },
            "required": ["seconds"],
        },
    },
    {
        "name": "list_timers",
        "description": "List running timers and how much time is left on each.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "save_note",
        "description": "Save a note or reminder-style memo the user wants to keep.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "read_notes",
        "description": "Read back the user's saved notes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "clear_notes",
        "description": "Delete all saved notes. Only call when the user clearly asks.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "open_website",
        "description": "Open a website in the default browser. Accepts a full URL or a domain like youtube.com.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "open_app",
        "description": "Open an app on this Windows PC. Known names: notepad, calculator, "
                       "file explorer, settings, task manager, chrome, edge, spotify, discord, "
                       "steam, vscode, word, excel, paint, terminal, snipping tool.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "media_control",
        "description": "Control music/video playback and system volume.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play_pause", "next", "previous", "volume_up", "volume_down", "mute"],
                },
                "steps": {"type": "integer", "minimum": 1, "maximum": 25,
                          "description": "For volume, how many notches (each is ~2%)."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "system_status",
        "description": "Battery level, charging state, CPU and memory usage of this laptop.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Windows launch commands. "start" handles URIs (ms-settings:, spotify:) and app aliases.
APPS = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "file explorer": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "files": ["explorer.exe"],
    "settings": "ms-settings:",
    "task manager": ["taskmgr.exe"],
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "spotify": "spotify:",
    "discord": "discord:",
    "steam": "steam:",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "word": "winword",
    "excel": "excel",
    "paint": ["mspaint.exe"],
    "terminal": "wt",
    "command prompt": ["cmd.exe"],
    "snipping tool": "ms-screenclip:",
}

# Tools that only read, so retrying after a network error can't do anything twice
READ_ONLY_PREFIXES = ("get_", "list_", "check_", "read_", "recall", "summarize_", "search_")

MEDIA_KEYS = {
    "play_pause": "play/pause media",
    "next": "next track",
    "previous": "previous track",
    "volume_up": "volume up",
    "volume_down": "volume down",
    "mute": "volume mute",
}

WEATHER_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
    65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers",
    81: "rain showers", 82: "violent rain showers", 95: "thunderstorms", 96: "thunderstorms with hail",
    99: "thunderstorms with hail",
}


class Tools(memory.MemoryTools, reminders.ReminderTools, calendar_tools.CalendarTools,
            email_tools.EmailTools, system_tools.SystemTools, location.LocationTools,
            home_assistant.HomeAssistantTools, profiles.ProfileTools):
    def __init__(self, on_timer_done=None, store: Store = None, cfg: dict = None, on_reminder=None,
                 confirm=None, on_profile_switch=None):
        # on_timer_done(label) and on_reminder(text, late) are called from background threads.
        # confirm(question, detail) -> bool asks the user before irreversible tools (see run()).
        # on_profile_switch(profile_id) lets the app save the active profile.
        self.on_timer_done = on_timer_done or (lambda label: None)
        self.confirm = confirm
        self.on_profile_switch = on_profile_switch
        self.timers = {}  # id -> (label, end_time)
        self._timer_id = 0
        self.cfg = cfg if cfg is not None else {}
        self.store = store or Store()
        self._import_old_notes()
        active = self.cfg.get("active_profile", profiles.DEFAULT)
        known = {p["id"] for p in profiles.all_profiles(self.store, self.cfg)}
        self.profile = active if active in known else profiles.DEFAULT
        self.locator = location.Locator(self.effective_cfg)  # uses the active person's home city
        self.reminder_scheduler = None
        if on_reminder and self.cfg.get("reminders_enabled", True):
            self.reminder_scheduler = reminders.ReminderScheduler(self.store, on_reminder).start()

    def schemas(self) -> list:
        """Tool definitions to send to Claude, leaving out features switched off in settings."""
        schemas = list(TOOL_SCHEMAS) + location.SCHEMAS
        if self.cfg.get("profiles_enabled", True):
            schemas += profiles.SCHEMAS
        if self.cfg.get("memory_enabled", True):
            schemas += memory.SCHEMAS
        if self.cfg.get("reminders_enabled", True):
            schemas += reminders.SCHEMAS
        if self.cfg.get("calendar_provider", "none") != "none":
            schemas += calendar_tools.SCHEMAS
        if self.cfg.get("email_provider", "none") != "none":
            schemas += email_tools.SCHEMAS
        if self.cfg.get("system_control_enabled", True):
            schemas += system_tools.SCHEMAS
        if self.cfg.get("ha_url") and self.cfg.get("ha_token"):
            schemas += home_assistant.SCHEMAS
        return schemas

    def memory_summary(self) -> list:
        if not self.cfg.get("memory_enabled", True):
            return []
        return memory.summary(self.store, self.profile)

    # ---------- dispatch ----------
    def needs_confirmation(self, name: str) -> bool:
        return name in self.cfg.get("confirm_tools", safety.DEFAULT_CONFIRM_TOOLS)

    def run(self, name: str, args: dict) -> tuple:
        """Run a tool for Claude. Returns (result text, is_error).

        Irreversible tools ask the user first through self.confirm; no answer, an unclear
        answer or no way to ask all count as no. Read-only tools retry once on a network
        blip. Errors come back as text so Claude can try another way or explain."""
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return f"Unknown tool: {name}", True
        args = args or {}
        if self.needs_confirmation(name):
            question, detail = safety.describe(name, args)
            if not (self.confirm and self.confirm(question, detail)):
                return ("The user did not confirm, so nothing was done. Don't retry; "
                        "ask what they'd like instead."), True
        attempts = 2 if name.startswith(READ_ONLY_PREFIXES) else 1
        for attempt in range(attempts):
            try:
                result = fn(**args)
                return (result if isinstance(result, str) else json.dumps(result)), False
            except requests.RequestException as e:
                if attempt + 1 < attempts:
                    time.sleep(1)
                    continue
                return f"Error running {name}: network problem ({type(e).__name__}). It may work if retried later.", True
            except Exception as e:
                return f"Error running {name}: {e}", True

    def dispatch(self, name: str, args: dict) -> str:
        return self.run(name, args)[0]

    # ---------- tools ----------
    def t_get_datetime(self):
        return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    def t_get_weather(self, location: str = ""):
        if not location.strip():
            here = self.locator.current()
            if here.lat is not None:
                return self._weather_at(here.lat, here.lon, here.name)
            if not here.name:
                return "I don't know where you are. Name a city, or set a home city in settings."
            location = here.name
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        ).json()
        if not geo.get("results"):
            # Open-Meteo's geocoder wants just the city; retry without ", State"
            short = location.split(",")[0].strip()
            if short != location:
                return self.t_get_weather(short)
            return f"Couldn't find a place called {location}."
        place = geo["results"][0]
        return self._weather_at(place["latitude"], place["longitude"],
                                f"{place['name']}, {place.get('admin1', '')}".strip(", "))

    def _weather_at(self, lat: float, lon: float, place_name: str):
        wx = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "forecast_days": 3,
            },
            timeout=10,
        ).json()
        cur, daily = wx["current"], wx["daily"]
        return {
            "place": place_name,
            "now": {
                "temp_f": cur["temperature_2m"],
                "feels_like_f": cur["apparent_temperature"],
                "humidity_pct": cur["relative_humidity_2m"],
                "wind_mph": cur["wind_speed_10m"],
                "conditions": WEATHER_CODES.get(cur["weather_code"], "unknown"),
            },
            "forecast": [
                {
                    "date": daily["time"][i],
                    "high_f": daily["temperature_2m_max"][i],
                    "low_f": daily["temperature_2m_min"][i],
                    "rain_chance_pct": daily["precipitation_probability_max"][i],
                    "conditions": WEATHER_CODES.get(daily["weather_code"][i], "unknown"),
                }
                for i in range(len(daily["time"]))
            ],
        }

    def t_set_timer(self, seconds: int, label: str = "timer"):
        self._timer_id += 1
        tid = self._timer_id
        self.timers[tid] = (label, time.time() + seconds)

        def fire():
            if self.timers.pop(tid, None) is not None:
                self.on_timer_done(label)

        t = threading.Timer(seconds, fire)
        t.daemon = True
        t.start()
        mins, secs = divmod(seconds, 60)
        return f"Timer '{label}' set for {mins}m {secs}s."

    def t_list_timers(self):
        if not self.timers:
            return "No timers running."
        now = time.time()
        return [
            {"label": label, "seconds_left": max(0, int(end - now))}
            for label, end in self.timers.values()
        ]

    def _import_old_notes(self):
        """Notes used to live in notes.json; move any into the database (default profile) once."""
        path = config.NOTES_PATH
        if not path.exists():
            return
        try:
            old = json.loads(path.read_text(encoding="utf-8")) or []
        except (OSError, json.JSONDecodeError):
            return  # leave an unreadable file alone rather than lose it
        for n in old:
            self.store.run("INSERT INTO notes (profile, text, saved) VALUES ('default', ?, ?)",
                           (n.get("text", ""), n.get("saved", "")))
        path.replace(path.with_name(path.name + ".imported"))

    def t_save_note(self, text: str):
        self.store.run("INSERT INTO notes (profile, text, saved) VALUES (?, ?, ?)",
                       (self.profile, text, datetime.now().strftime("%Y-%m-%d %H:%M")))
        count = self.store.query("SELECT COUNT(*) AS n FROM notes WHERE profile = ?", (self.profile,))[0]["n"]
        return f"Saved. You have {count} note(s)."

    def t_read_notes(self):
        notes = self.store.query("SELECT text, saved FROM notes WHERE profile = ? ORDER BY id", (self.profile,))
        return notes if notes else "No notes saved."

    def t_clear_notes(self):
        self.store.run("DELETE FROM notes WHERE profile = ?", (self.profile,))
        return "All notes deleted."

    def t_open_website(self, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return f"Opened {url}"

    def t_open_app(self, name: str):
        key = name.lower().strip()
        target = APPS.get(key)
        if target is None:
            # last resort: anything on PATH with that exact name
            exe = shutil.which(key) or shutil.which(key.replace(" ", ""))
            if not exe:
                return f"I don't know how to open '{name}' yet."
            target = [exe]
        if os.name != "nt":
            return f"(Would open {name} on Windows.)"
        if isinstance(target, list):
            subprocess.Popen(target, close_fds=True)
        else:
            # 'start' resolves App Paths aliases (chrome, winword) and URI schemes
            subprocess.Popen(["cmd", "/c", "start", "", target], close_fds=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return f"Opening {name}."

    def t_media_control(self, action: str, steps: int = 5):
        if keyboard is None:
            return "Media control isn't available on this system."
        key = MEDIA_KEYS[action]
        repeat = steps if action in ("volume_up", "volume_down") else 1
        for _ in range(repeat):
            keyboard.send(key)
            time.sleep(0.02)
        return f"Done: {action.replace('_', ' ')}."

    def t_system_status(self):
        if psutil is None:
            return "System info unavailable."
        info = {
            "cpu_pct": psutil.cpu_percent(interval=0.5),
            "memory_pct": psutil.virtual_memory().percent,
        }
        batt = psutil.sensors_battery()
        if batt:
            info["battery_pct"] = round(batt.percent)
            info["plugged_in"] = batt.power_plugged
            if not batt.power_plugged and batt.secsleft not in (psutil.POWER_TIME_UNLIMITED,
                                                                  psutil.POWER_TIME_UNKNOWN):
                info["battery_minutes_left"] = batt.secsleft // 60
        return info
