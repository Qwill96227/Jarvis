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
