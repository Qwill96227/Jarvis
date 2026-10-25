"""Guards around tool calls: which actions need the user's confirmation, how to describe
them, and reading a spoken yes/no. The gate itself is in Tools.run, so it's enforced in
code and Claude can't skip it."""
import re

# Irreversible by default. Overridable with the "confirm_tools" setting.
DEFAULT_CONFIRM_TOOLS = ["send_email", "clear_notes"]


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
