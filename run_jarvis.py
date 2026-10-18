"""Entry point. `python run_jarvis.py` to run from source; PyInstaller builds from this too."""
import os
import sys
import traceback
from pathlib import Path

# In the windowed .exe there is no console, so stdout/stderr are None and any
# library that prints (download progress bars etc.) would crash. Send them to a log.
LOG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Jarvis"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "jarvis.log"
if sys.stdout is None or sys.stderr is None:
    _log = open(LOG_PATH, "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log


def _show_crash(msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "Drexya couldn't start", 0x10)
    except Exception:
        print(msg)


if __name__ == "__main__":
    try:
        from jarvis.app import main
        main()
    except Exception:
        tb = traceback.format_exc()
        (LOG_DIR / "crash.log").write_text(tb, encoding="utf-8")
        print(tb, file=sys.stderr)
        _show_crash(f"{tb[-1500:]}\n\nFull log saved to:\n{LOG_DIR / 'crash.log'}")
