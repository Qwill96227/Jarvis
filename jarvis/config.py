"""Settings stored in %APPDATA%\\Jarvis\\config.json (or ~/.jarvis on non-Windows)."""
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
VOICES_DIR = APP_DIR / "voices"

DEFAULTS = {
    "api_key": "",
    "model": "claude-haiku-5-5",
    "user_name": "",
    "home_city": "",
    "voice_enabled": True,
    "piper_voice": "en_GB-alan-medium",   # British male, very Jarvis
    "whisper_model": "base.en",           # tiny.en = faster, small.en = more accurate
    "hotkey": "ctrl+alt+j",
    "web_search": True,
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
