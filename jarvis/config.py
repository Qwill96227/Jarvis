"""Settings stored in %APPDATA%\\Jarvis\\config.json (or ~/.jarvis on non-Windows).
The folder keeps its original name from before the rename to Drexya, so existing
installs keep their API key, settings and downloaded voice."""
import json
import os
from pathlib import Path

if os.name == "nt":
    APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Jarvis"
else:
    APP_DIR = Path.home() / ".jarvis"

APP_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = APP_DIR / "config.json"
NOTES_PATH = APP_DIR / "notes.json"
DB_PATH = APP_DIR / "drexya.db"           # memory, reminders, profiles, audit log
GOOGLE_CLIENT_PATH = APP_DIR / "google_client.json"  # OAuth client you download from Google Cloud
GOOGLE_TOKEN_PATH = APP_DIR / "google_token.json"    # written after you click Connect Google
WAKEWORD_DIR = APP_DIR / "wakeword"                  # downloaded wake word models
VOICES_DIR = APP_DIR / "voices"

# Claude models offered in settings: id -> (menu label, note shown under the menu)
MODELS = {
    "claude-haiku-5-5": ("Haiku 5.5 (fastest, cheapest)",
                         "Quick everyday answers. Well under a cent per question."),
    "claude-sonnet-5-5": ("Sonnet 5.5 (smarter)",
                          "Better at explaining and planning. About 20x Haiku's cost, a bit slower."),
    "claude-opus-5-5": ("Opus 5.5 (smartest everyday)",
                        "Best for hard questions. About 40x Haiku's cost, slower to reply."),
    "claude-fable-5-1": ("Fable 5.1 (most capable)",
                         "Heads up: burns credits fastest (about 100x Haiku) and is the slowest to reply."),
}

DEFAULTS = {
    "api_key": "",
    "model": "claude-haiku-5-5",
    "user_name": "",
    "home_city": "",
    "voice_enabled": True,
    "piper_voice": "en_GB-alan-medium",   # British male
    "whisper_model": "base.en",           # tiny.en = faster, small.en = more accurate
    "hotkey": "ctrl+alt+j",
    "web_search": True,
    "memory_enabled": True,               # remember/recall/forget + known facts in the prompt
    "reminders_enabled": True,            # date/time reminders that survive restarts
    "calendar_provider": "none",          # none / google (outlook later)
    "email_provider": "none",             # none / google (Gmail; outlook later)
    "system_control_enabled": True,       # windows, screenshots, files, brightness, Wi-Fi
    "location_mode": "auto",              # auto (Windows, then IP, then home city) / ip / home
    "ha_url": "",                         # Home Assistant, e.g. http://homeassistant.local:8123
    "ha_token": "",                       # Home Assistant long-lived access token
    "wake_word_enabled": False,           # always-on listening; off by default to save battery
    "wake_word": "hey_jarvis",            # hey_jarvis / alexa / hey_mycroft, or a path to a custom .onnx
    "wake_word_threshold": 0.5,           # 0-1; raise if it triggers by mistake, lower if it misses you
    "confirm_tools": ["send_email", "clear_notes"],  # ask before these (add move_file, close_app...)
    "max_tool_steps": 12,                 # tool round-trips allowed for one request
    "profiles_enabled": True,             # several people with their own notes/memories/reminders
    "active_profile": "default",          # "default" = the main settings' name and city
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
