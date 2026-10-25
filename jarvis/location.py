"""Where is the user right now? Tries the Windows location service, then IP geolocation,
then falls back to the home city from settings. Results are cached for a few minutes.

location_mode setting:
  auto - Windows location, then IP lookup, then home city (default)
  ip   - IP lookup, then home city (skips Windows location)
  home - always the home city; nothing leaves the PC
"""
import math
import subprocess
import time
from dataclasses import dataclass

import requests

CACHE_SECONDS = 600

SCHEMAS = [
    {
        "name": "get_location",
        "description": "Where the user is right now (city), and how it was worked out.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

WINDOWS_SCRIPT = r"""
Add-Type -AssemblyName System.Device
$w = New-Object System.Device.Location.GeoCoordinateWatcher
$w.Start()
for ($i = 0; $i -lt 50 -and $w.Status -ne 'Ready' -and $w.Permission -ne 'Denied'; $i++) { Start-Sleep -Milliseconds 100 }
if ($w.Permission -eq 'Denied') { 'DENIED' }
elseif ($w.Status -eq 'Ready') { $c = $w.Position.Location; '{0},{1}' -f $c.Latitude, $c.Longitude }
else { 'UNAVAILABLE' }
$w.Stop()
"""


@dataclass
class Location:
    name: str          # "Baton Rouge, Louisiana"
    lat: float = None  # None when only a city name is known (home city fallback)
    lon: float = None
    source: str = ""   # "Windows location" / "IP address" / "home city"


def _windows_coords():
    """(lat, lon) from the Windows location service, or None (off, denied or no fix in 5s)."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", WINDOWS_SCRIPT],
        capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()
    try:
        lat, lon = (float(v) for v in out.split(","))
    except ValueError:
        return None
    return None if math.isnan(lat) or math.isnan(lon) else (lat, lon)


def _reverse_geocode(lat, lon) -> str:
    r = requests.get("https://api.bigdatacloud.net/data/reverse-geocode-client",
                     params={"latitude": lat, "longitude": lon, "localityLanguage": "en"}, timeout=8).json()
    city = r.get("city") or r.get("locality") or ""
    return ", ".join(p for p in (city, r.get("principalSubdivision", "")) if p) or f"{lat:.2f}, {lon:.2f}"


def windows_location():
    coords = _windows_coords()
    if not coords:
        return None
    return Location(_reverse_geocode(*coords), coords[0], coords[1], "Windows location")


def ip_location():
    data = requests.get("https://ipinfo.io/json", timeout=8).json()
    if not data.get("loc") or not data.get("city"):
        return None
    lat, lon = (float(v) for v in data["loc"].split(","))
    name = ", ".join(p for p in (data["city"], data.get("region", "")) if p)
    return Location(name, lat, lon, "IP address")


class Locator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._cache = None  # (mode, time, Location)

    def current(self) -> Location:
        mode = self.cfg.get("location_mode", "auto")
        if self._cache and self._cache[0] == mode and time.monotonic() - self._cache[1] < CACHE_SECONDS:
            return self._cache[2]
        steps = {"auto": [windows_location, ip_location], "ip": [ip_location]}.get(mode, [])
        loc = None
        for step in steps:
            try:
                loc = step()
            except Exception as e:  # network down, PowerShell missing, bad JSON...
                print(f"[location] {step.__name__} failed: {e}")
            if loc:
                break
        if loc is None:
            home = self.cfg.get("home_city", "").strip()
            if not home:
                return Location("", source="unknown")  # not cached: settings may change
            loc = Location(home, source="home city")
        self._cache = (mode, time.monotonic(), loc)
        return loc


class LocationTools:
    """Mixin for Tools. Needs self.locator."""

    def t_get_location(self):
        loc = self.locator.current()
        if not loc.name:
            return "I don't know where you are. Set a home city in settings."
        return {"place": loc.name, "based_on": loc.source}
