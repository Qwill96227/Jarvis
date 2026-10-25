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

from . import config, memory, reminders
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
        "description": "Current conditions and a 3-day forecast for a city. "
                       "If the user doesn't name a place, use their home city.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string", "description": "City name, e.g. 'Baton Rouge'"}},
            "required": ["location"],
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


class Tools(memory.MemoryTools, reminders.ReminderTools):
    def __init__(self, on_timer_done=None, store: Store = None, cfg: dict = None, on_reminder=None):
        # on_timer_done(label) and on_reminder(text, late) are called from background threads
        self.on_timer_done = on_timer_done or (lambda label: None)
        self.timers = {}  # id -> (label, end_time)
        self._timer_id = 0
        self.cfg = cfg if cfg is not None else {}
        self.store = store or Store()
        self.profile = "default"
        self.reminder_scheduler = None
        if on_reminder and self.cfg.get("reminders_enabled", True):
            self.reminder_scheduler = reminders.ReminderScheduler(self.store, on_reminder).start()

    def schemas(self) -> list:
        """Tool definitions to send to Claude, leaving out features switched off in settings."""
        schemas = list(TOOL_SCHEMAS)
        if self.cfg.get("memory_enabled", True):
            schemas += memory.SCHEMAS
        if self.cfg.get("reminders_enabled", True):
            schemas += reminders.SCHEMAS
        return schemas

    def memory_summary(self) -> list:
        if not self.cfg.get("memory_enabled", True):
            return []
        return memory.summary(self.store, self.profile)

    # ---------- dispatch ----------
    def dispatch(self, name: str, args: dict) -> str:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return f"Unknown tool: {name}"
        try:
            result = fn(**(args or {}))
            return result if isinstance(result, str) else json.dumps(result)
        except Exception as e:  # report errors back to Claude so it can recover
            return f"Error running {name}: {e}"

    # ---------- tools ----------
    def t_get_datetime(self):
        return datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    def t_get_weather(self, location: str):
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
        wx = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": place["latitude"],
                "longitude": place["longitude"],
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
            "place": f"{place['name']}, {place.get('admin1', '')}".strip(", "),
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

    def _notes(self):
        if config.NOTES_PATH.exists():
            try:
                return json.loads(config.NOTES_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
        return []

    def t_save_note(self, text: str):
        notes = self._notes()
        notes.append({"text": text, "saved": datetime.now().strftime("%Y-%m-%d %H:%M")})
        config.NOTES_PATH.write_text(json.dumps(notes, indent=2), encoding="utf-8")
        return f"Saved. You have {len(notes)} note(s)."

    def t_read_notes(self):
        notes = self._notes()
        return notes if notes else "No notes saved."

    def t_clear_notes(self):
        config.NOTES_PATH.write_text("[]", encoding="utf-8")
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
