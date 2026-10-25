"""Deeper Windows control: close apps, list/switch windows, screenshots, file search/open/move,
screen brightness and Wi-Fi.

Safety limits:
- close_app asks apps to close normally (like clicking X), so unsaved work still prompts.
  Core Windows processes can't be closed.
- File tools only touch files inside the user's profile folder. open_file won't run
  programs or scripts, and move_file never overwrites. There is no delete tool.
"""
import ctypes
import fnmatch
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

HOME = Path.home()
FOLDERS = {
    "home": HOME, "desktop": HOME / "Desktop", "documents": HOME / "Documents",
    "downloads": HOME / "Downloads", "pictures": HOME / "Pictures", "music": HOME / "Music",
    "videos": HOME / "Videos",
}
# OneDrive often redirects Desktop/Documents/Pictures; prefer those copies when they exist
for _name in ("Desktop", "Documents", "Pictures"):
    if (HOME / "OneDrive" / _name).is_dir():
        FOLDERS[_name.lower()] = HOME / "OneDrive" / _name

# Friendly name -> process image name, for apps whose process isn't just "<name>.exe"
PROCESS_NAMES = {
    "chrome": "chrome.exe", "google chrome": "chrome.exe", "edge": "msedge.exe",
    "microsoft edge": "msedge.exe", "spotify": "spotify.exe", "discord": "discord.exe",
    "steam": "steam.exe", "vscode": "code.exe", "vs code": "code.exe", "visual studio code": "code.exe",
    "word": "winword.exe", "excel": "excel.exe", "powerpoint": "powerpnt.exe", "outlook": "outlook.exe",
    "teams": "ms-teams.exe", "notepad": "notepad.exe", "calculator": "calculatorapp.exe",
    "paint": "mspaint.exe", "terminal": "windowsterminal.exe", "firefox": "firefox.exe",
    "zoom": "zoom.exe", "task manager": "taskmgr.exe",
}
PROTECTED = {"explorer.exe", "svchost.exe", "winlogon.exe", "csrss.exe", "lsass.exe", "services.exe",
             "smss.exe", "wininit.exe", "dwm.exe", "system", "registry", "fontdrvhost.exe",
             "python.exe", "pythonw.exe", "drexya.exe"}
# Things open_file must never launch: it opens documents, not programs
RUNNABLE = {".exe", ".bat", ".cmd", ".com", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf",
            ".wsh", ".msi", ".msp", ".scr", ".pif", ".lnk", ".reg", ".hta", ".cpl", ".jar", ".py", ".pyw"}
SEARCH_LIMIT = 10
SEARCH_SECONDS = 6
SKIP_DIRS = {"appdata", "node_modules", ".git", "$recycle.bin", ".venv", "__pycache__"}

SCHEMAS = [
    {
        "name": "close_app",
        "description": "Close an app, like clicking its X. Apps with unsaved work will still ask to save.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "list_windows",
        "description": "List the open windows (app and title).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "switch_window",
        "description": "Bring a window to the front by words from its title or its app name.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "take_screenshot",
        "description": "Screenshot all screens and save it to Pictures\\Screenshots.",
        "input_schema": {
            "type": "object",
            "properties": {"open_after": {"type": "boolean", "description": "Open the image afterwards."}},
        },
    },
    {
        "name": "search_files",
        "description": "Find files by name in the user's folders. Use * as a wildcard, e.g. '*.pdf' or 'resume*'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Part of the file name, or a wildcard pattern."},
                "folder": {"type": "string", "enum": list(FOLDERS),
                           "description": "Where to look. Defaults to home (all of them)."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "open_file",
        "description": "Open a document, picture, video or folder with its default app. Use a path from "
                       "search_files. Won't run programs or scripts.",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    },
    {
        "name": "move_file",
        "description": "Move a file into another folder. Use a path from search_files. Never overwrites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "to_folder": {"type": "string",
                              "description": "A folder name from search_files' list (e.g. 'documents') or a full path."},
            },
            "required": ["path", "to_folder"],
        },
    },
    {
        "name": "set_brightness",
        "description": "Set the built-in screen's brightness (laptops only). Give a level, or a change like +20.",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "minimum": 0, "maximum": 100},
                "change": {"type": "integer", "minimum": -100, "maximum": 100},
            },
        },
    },
    {
        "name": "wifi_control",
        "description": "Wi-Fi: status (current network and signal), list saved networks, connect to a saved "
                       "network, or disconnect.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "list", "connect", "disconnect"]},
                "network": {"type": "string", "description": "Saved network name, for connect."},
            },
            "required": ["action"],
        },
    },
]


# ---------------------------------------------------------------- helpers
def _run(cmd: list, timeout=15) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return (out.stdout or "") + (out.stderr or "")


def _powershell(script: str) -> str:
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script]).strip()


def process_name(name: str) -> str:
    key = name.lower().strip()
    if key in PROCESS_NAMES:
        return PROCESS_NAMES[key]
    return key if key.endswith(".exe") else key.replace(" ", "") + ".exe"


def inside_home(path, root: Path = None) -> Path:
    """Resolve path and make sure it's inside the user's profile. Raises ValueError if not."""
    root = (root or HOME).resolve()
    p = Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
    if p != root and root not in p.parents:
        raise ValueError("I can only work with files in your user folders.")
    return p


def parse_netsh(text: str) -> dict:
    """'    Key   : value' lines -> {'key': 'value'} (first occurrence wins)."""
    info = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([^:]+?)\s*:\s*(.*)$", line)
        if m and m.group(1).lower() not in info:
            info[m.group(1).lower()] = m.group(2).strip()
    return info


def search(pattern: str, roots, limit=SEARCH_LIMIT, seconds=SEARCH_SECONDS) -> list:
    """Case-insensitive name search under roots, skipping hidden/app folders. Newest first."""
    pat = pattern.lower().strip()
    if not any(c in pat for c in "*?"):
        pat = f"*{pat}*"
    deadline = time.monotonic() + seconds
    found, seen = [], set()
    stack = [Path(r) for r in roots]
    while stack and time.monotonic() < deadline:
        folder = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            name = e.name.lower()
            if name.startswith(".") or name in SKIP_DIRS:
                continue
            if e.is_dir(follow_symlinks=False):
                stack.append(Path(e.path))
            elif fnmatch.fnmatch(name, pat) and e.path not in seen:
                seen.add(e.path)
                found.append(Path(e.path))
    found.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return found[:limit]


# ---------------------------------------------------------------- windows (Win32 via ctypes)
def _windows() -> list:
    """Visible top-level windows with a title: [(hwnd, title, process name)]."""
    if os.name != "nt":
        return []
    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):  # skip owned popups
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:  # hidden UWP / other-desktop windows
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            proc = psutil.Process(pid.value).name() if psutil else ""
        except Exception:
            proc = ""
        if buf.value not in ("Program Manager", "Windows Input Experience"):
            result.append((hwnd, buf.value, proc))
        return True

    user32.EnumWindows(callback, 0)
    return result


def _focus(hwnd):
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    # Windows only lets the foreground app change focus; a synthetic Alt tap lifts that lock
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


class SystemTools:
    """Mixin for Tools."""

    def t_close_app(self, name: str):
        proc = process_name(name)
        if proc in PROTECTED:
            return f"I won't close {name}; Windows or I need it."
        if psutil and not any((p.info["name"] or "").lower() == proc for p in psutil.process_iter(["name"])):
            return f"{name} isn't running."
        out = _run(["taskkill", "/IM", proc])  # no /F: polite close, so apps can ask to save
        if "SUCCESS" in out.upper():
            return f"Closing {name}."
        return f"{name} didn't close; it may be asking to save something."

    def t_list_windows(self):
        wins = _windows()
        if not wins:
            return "No open windows."
        return [{"app": proc.removesuffix(".exe"), "title": title} for _, title, proc in wins[:25]]

    def t_switch_window(self, name: str):
        q = name.lower().strip()
        target = process_name(name).removesuffix(".exe")
        matches = [w for w in _windows() if q in w[1].lower() or w[2].lower().removesuffix(".exe") in (q, target)]
        if not matches:
            return f"I can't see a window for {name}."
        _focus(matches[0][0])
        return f"Switched to {matches[0][1]}."

    def t_take_screenshot(self, open_after: bool = False):
        from PIL import ImageGrab
        folder = FOLDERS["pictures"] / "Screenshots"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"Drexya {datetime.now():%Y-%m-%d %H%M%S}.png"
        ImageGrab.grab(all_screens=True).save(path)
        if open_after:
            os.startfile(path)
        return f"Saved the screenshot to Pictures, Screenshots, as {path.name}."

    def t_search_files(self, name: str, folder: str = "home"):
        hits = search(name, [FOLDERS.get(folder, HOME)])
        if not hits:
            return f"No files matching '{name}'."
        return [{"name": p.name, "folder": str(p.parent).replace(str(HOME), "~"), "path": str(p),
                 "modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")} for p in hits]

    def t_open_file(self, path: str):
        p = inside_home(path)
        if not p.exists():
            return "That file doesn't exist."
        if p.suffix.lower() in RUNNABLE:
            return "I don't open programs or scripts from files; that's a safety rule."
        os.startfile(p)
        return f"Opening {p.name}."

    def t_move_file(self, path: str, to_folder: str):
        src = inside_home(path)
        if not src.is_file():
            return "That file doesn't exist."
        dest_dir = inside_home(FOLDERS.get(to_folder.lower().strip(), to_folder))
        if not dest_dir.is_dir():
            return f"There's no folder called {to_folder}."
        dest = dest_dir / src.name
        if dest.exists():
            return f"There's already a {src.name} in that folder, so I left it where it is."
        src.rename(dest)
        return f"Moved {src.name} to {dest_dir.name}."

    def t_set_brightness(self, level: int = None, change: int = None):
        if level is None and change is None:
            return "Give a brightness level or a change."
        current = _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness "
                              "-ErrorAction Stop | Select-Object -First 1).CurrentBrightness")
        if not current.isdigit():
            return "This screen's brightness can't be set from software; it's probably an external monitor."
        new = level if level is not None else int(current) + change
        new = max(0, min(100, new))
        _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | "
                    f"Select-Object -First 1) | Invoke-CimMethod -MethodName WmiSetBrightness "
                    f"-Arguments @{{Timeout=0; Brightness={new}}} | Out-Null")
        return f"Brightness set to {new} percent."

    def t_wifi_control(self, action: str, network: str = ""):
        out = _run(["netsh", "wlan", "show", "interfaces"])
        if "wlansvc" in out.lower() or "no wireless interface" in out.lower():
            return "This PC isn't using Wi-Fi, or its Wi-Fi is switched off."
        if action == "status":
            info = parse_netsh(out)
            if info.get("state", "").lower() != "connected":
                return "Wi-Fi is on but not connected."
            return {"network": info.get("ssid", "?"), "signal": info.get("signal", "?")}
        if action == "list":
            names = re.findall(r"All User Profile\s*:\s*(.+)", _run(["netsh", "wlan", "show", "profiles"]))
            return [n.strip() for n in names] or "No saved Wi-Fi networks."
        if action == "disconnect":
            _run(["netsh", "wlan", "disconnect"])
            return "Disconnected from Wi-Fi."
        if action == "connect":
            if not network:
                return "Which network?"
            result = _run(["netsh", "wlan", "connect", f"name={network}"])
            if "successfully" in result.lower():
                return f"Connecting to {network}."
            return f"Couldn't connect to {network}. It has to be a network this PC has joined before."
        return f"Unknown Wi-Fi action: {action}"
