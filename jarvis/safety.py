"""Guards around tool calls: which actions need confirmation or a PIN, how to describe
them, reading a spoken yes/no, PIN hashing, and the audit log. The gate itself is in
Tools.run, so it's enforced in code and Claude can't skip it."""
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta

# Irreversible by default. Overridable with the "confirm_tools" setting.
DEFAULT_CONFIRM_TOOLS = ["send_email", "clear_notes"]
# Need the PIN (when one is set). Overridable with the "pin_tools" setting.
DEFAULT_PIN_TOOLS = ["send_email", "clear_notes", "move_file"]
PIN_ATTEMPTS = 3
AUDIT_DAYS = 90
PBKDF2_ROUNDS = 200_000
SECRET_KEYS = re.compile(r"token|password|secret|api_?key|pin", re.I)


# ---------------------------------------------------------------- PIN
def valid_pin(pin: str) -> bool:
    return bool(re.fullmatch(r"\d{4,8}", pin or ""))


def hash_pin(pin: str) -> str:
    """Salted PBKDF2 hash, safe to keep in config.json. The PIN itself is never stored."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_pin(stored: str, pin: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
        attempt = hashlib.pbkdf2_hmac("sha256", (pin or "").encode(), bytes.fromhex(salt), int(rounds))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(attempt.hex(), digest)


# ---------------------------------------------------------------- audit log
def _clean(value, key=""):
    if SECRET_KEYS.search(key):
        return "***"
    if isinstance(value, str) and len(value) > 120:
        return value[:117] + "..."
    if isinstance(value, dict):
        return {k: _clean(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value[:10]]
    return value


def log_call(store, profile: str, tool: str, args: dict, outcome: str, detail: str = ""):
    store.run("INSERT INTO audit (ts, profile, tool, args, outcome, detail) VALUES (?, ?, ?, ?, ?, ?)",
              (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), profile, tool,
               json.dumps(_clean(args or {}), ensure_ascii=False), outcome, (detail or "")[:200]))


def prune(store, days: int = AUDIT_DAYS):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    store.run("DELETE FROM audit WHERE ts < ?", (cutoff,))


def recent(store, profile: str = None, limit: int = 200) -> list:
    if profile is None:
        return store.query("SELECT ts, profile, tool, args, outcome, detail FROM audit ORDER BY id DESC LIMIT ?",
                           (limit,))
    return store.query("SELECT ts, tool, args, outcome FROM audit WHERE profile = ? ORDER BY id DESC LIMIT ?",
                       (profile, limit))


AUDIT_SCHEMAS = [
    {
        "name": "recent_activity",
        "description": "What you (Drexya) have done recently for this person: actions taken, failed or declined. "
                       "Use for 'what have you done today?' and similar.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Defaults to 15."}},
        },
    },
]


class AuditTools:
    """Mixin for Tools. Needs self.store and self.profile."""

    def t_recent_activity(self, limit: int = 15):
        rows = [r for r in recent(self.store, self.profile, max(1, min(limit, 50)) + 1) if r["tool"] != "recent_activity"]
        if not rows:
            return "Nothing done yet."
        return [{"when": r["ts"], "action": r["tool"].replace("_", " "), "outcome": r["outcome"]} for r in rows[:limit]]


def describe(name: str, args: dict) -> tuple:
    """(short spoken question, longer detail for the dialog) for a tool that needs confirming."""
    if name == "send_email":
        return (f"Send this email to {args.get('to', '?')}?",
                f"To: {args.get('to', '')}\nSubject: {args.get('subject', '')}\n\n{args.get('body', '')}")
    if name == "clear_notes":
        return "Delete all your notes?", "Every saved note will be deleted. This can't be undone."
    if name == "move_file":
        return (f"Move {args.get('path', '?').split(chr(92))[-1]} to {args.get('to_folder', '?')}?",
                f"From: {args.get('path', '')}\nTo: {args.get('to_folder', '')}")
    if name == "close_app":
        return f"Close {args.get('name', '?')}?", "Unsaved work may be lost if the app doesn't ask."
    readable = ", ".join(f"{k}: {v}" for k, v in (args or {}).items())
    return f"OK to {name.replace('_', ' ')}?", readable


YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "correct", "affirmative",
       "absolutely", "definitely", "please"}
YES_PHRASES = ("do it", "go ahead", "send it", "go for it", "that's right", "sounds good")
NO = {"no", "nope", "nah", "cancel", "stop", "don't", "dont", "wait", "negative", "never"}
NO_PHRASES = ("never mind", "nevermind", "hold on", "not yet", "hang on")


def parse_yes_no(text: str):
    """True for yes, False for no, None if unclear (unclear counts as no at the gate)."""
    t = text.lower().strip().replace("’", "'")
    words = set(re.findall(r"[a-z']+", t))
    negated = any(n in t for n in ("don't", "dont", "do not"))  # "don't send it" is a no, not both
    yes = not negated and (bool(words & YES) or any(p in t for p in YES_PHRASES))
    no = bool(words & NO) or any(p in t for p in NO_PHRASES)
    if yes and not no:
        return True
    if no and not yes:
        return False
    return None
