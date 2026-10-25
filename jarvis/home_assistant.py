"""Smart home control through Home Assistant's REST API (long-lived access token).

Only lights, switches, fans and thermostats are exposed. Locks, garage doors, alarms and
cameras are deliberately left out: they need more safeguards than a voice command.
"""
import difflib

import requests

CONTROLLABLE = ("light", "switch", "fan")
DOMAINS = CONTROLLABLE + ("climate",)
KINDS = {"lights": ("light",), "switches": ("switch",), "fans": ("fan",), "thermostats": ("climate",),
         "all": DOMAINS}

SCHEMAS = [
    {
        "name": "list_devices",
        "description": "List smart home devices and their state (on/off, brightness, temperature).",
        "input_schema": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": list(KINDS), "description": "Defaults to all."}},
        },
    },
    {
        "name": "control_device",
        "description": "Turn a light, switch or fan on, off or toggle it, by its name. For lights you can also "
                       "set brightness. If several devices match you get them back; ask which one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Device name, e.g. 'kitchen light'."},
                "action": {"type": "string", "enum": ["on", "off", "toggle"]},
                "brightness_pct": {"type": "integer", "minimum": 1, "maximum": 100,
                                   "description": "Lights only. Implies on."},
            },
            "required": ["name", "action"],
        },
    },
    {
        "name": "set_thermostat",
        "description": "Set a thermostat's target temperature and/or mode. Name can be omitted if there's only one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "temperature": {"type": "number", "description": "In the units Home Assistant uses."},
                "mode": {"type": "string", "enum": ["heat", "cool", "heat_cool", "auto", "off"]},
            },
        },
    },
]


class HomeAssistantError(Exception):
    """A problem talking to Home Assistant, worded for the user."""


class HomeAssistant:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _request(self, method, path, **kw):
        try:
            r = requests.request(method, f"{self.url}{path}", headers=self.headers, timeout=10, **kw)
        except requests.RequestException:
            raise HomeAssistantError(f"I can't reach Home Assistant at {self.url}.") from None
        if r.status_code == 401:
            raise HomeAssistantError("Home Assistant rejected the access token. Check it in settings.")
        if r.status_code >= 400:
            raise HomeAssistantError(f"Home Assistant returned an error ({r.status_code}).")
        return r.json() if r.content else None

    def states(self) -> list:
        return [s for s in self._request("GET", "/api/states") if s["entity_id"].split(".")[0] in DOMAINS]

    def call(self, domain: str, service: str, data: dict):
        return self._request("POST", f"/api/services/{domain}/{service}", json=data)


def friendly(state: dict) -> str:
    return state.get("attributes", {}).get("friendly_name") or state["entity_id"]


def describe(state: dict) -> dict:
    domain = state["entity_id"].split(".")[0]
    attrs = state.get("attributes", {})
    item = {"name": friendly(state), "type": domain, "state": state["state"]}
    if domain == "light" and attrs.get("brightness") is not None:
        item["brightness_pct"] = round(attrs["brightness"] / 255 * 100)
    if domain == "climate":
        item.update({k: attrs[k] for k in ("current_temperature", "temperature") if attrs.get(k) is not None})
    return item


def match(states: list, name: str) -> list:
    """Devices matching a spoken name: exact name/entity id, then substring, then close spelling."""
    q = name.lower().strip().removeprefix("the ").strip()
    for words in (q, q.removesuffix("s")):  # "kitchen lights" -> "kitchen light"
        exact = [s for s in states if friendly(s).lower() == words or s["entity_id"].lower() == words]
        if exact:
            return exact
    sub = [s for s in states if q in friendly(s).lower() or q.replace(" ", "_") in s["entity_id"]]
    if sub:
        return sub
    names = {friendly(s).lower(): s for s in states}
    return [names[n] for n in difflib.get_close_matches(q, names, n=3, cutoff=0.6)]


class HomeAssistantTools:
    """Mixin for Tools. Needs self.cfg."""

    def home(self) -> HomeAssistant:
        url, token = self.cfg.get("ha_url", "").strip(), self.cfg.get("ha_token", "").strip()
        if not url or not token:
            raise HomeAssistantError("Home Assistant isn't set up. Add its address and token in settings.")
        return HomeAssistant(url, token)

    def t_list_devices(self, kind: str = "all"):
        try:
            states = self.home().states()
        except HomeAssistantError as e:
            return str(e)
        devices = [describe(s) for s in states if s["entity_id"].split(".")[0] in KINDS.get(kind, DOMAINS)]
        return devices[:40] if devices else "No devices like that in Home Assistant."

    def t_control_device(self, name: str, action: str, brightness_pct: int = None):
        try:
            ha = self.home()
            found = [s for s in match(ha.states(), name) if s["entity_id"].split(".")[0] in CONTROLLABLE]
            if not found:
                return f"I can't find a light, switch or fan called {name}."
            if len(found) > 1:
                return {"several_match": [friendly(s) for s in found], "note": "Ask the user which one."}
            entity = found[0]["entity_id"]
            domain = entity.split(".")[0]
            data = {"entity_id": entity}
            if brightness_pct is not None and domain == "light":
                data["brightness_pct"] = brightness_pct
                action = "on"
            ha.call(domain, {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[action], data)
        except HomeAssistantError as e:
            return str(e)
        done = f"set to {brightness_pct} percent" if "brightness_pct" in data else \
            "toggled" if action == "toggle" else f"turned {action}"
        return f"{friendly(found[0])} {done}."

    def t_set_thermostat(self, name: str = "", temperature: float = None, mode: str = ""):
        if temperature is None and not mode:
            return "Give a temperature or a mode."
        try:
            ha = self.home()
            thermostats = [s for s in ha.states() if s["entity_id"].startswith("climate.")]
            found = match(thermostats, name) if name else thermostats
            if not found:
                return "I can't find a thermostat" + (f" called {name}." if name else " in Home Assistant.")
            if len(found) > 1:
                return {"several_match": [friendly(s) for s in found], "note": "Ask the user which one."}
            entity = found[0]["entity_id"]
            if mode:
                ha.call("climate", "set_hvac_mode", {"entity_id": entity, "hvac_mode": mode})
            if temperature is not None:
                ha.call("climate", "set_temperature", {"entity_id": entity, "temperature": temperature})
        except HomeAssistantError as e:
            return str(e)
        parts = ([f"mode {mode}"] if mode else []) + ([f"{temperature:g} degrees"] if temperature is not None else [])
        return f"{friendly(found[0])} set to {' and '.join(parts)}."
