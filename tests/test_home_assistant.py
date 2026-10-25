import json
from unittest import mock

import requests

from jarvis import home_assistant

from .helpers import ToolsTestCase

STATES = [
    {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen Light", "brightness": 128}},
    {"entity_id": "light.bedroom_lamp", "state": "off", "attributes": {"friendly_name": "Bedroom Lamp"}},
    {"entity_id": "light.bedroom_ceiling", "state": "off", "attributes": {"friendly_name": "Bedroom Ceiling"}},
    {"entity_id": "switch.coffee_maker", "state": "off", "attributes": {"friendly_name": "Coffee Maker"}},
    {"entity_id": "climate.hallway", "state": "heat",
     "attributes": {"friendly_name": "Hallway Thermostat", "current_temperature": 68, "temperature": 70}},
    {"entity_id": "lock.front_door", "state": "locked", "attributes": {"friendly_name": "Front Door"}},
    {"entity_id": "sensor.outside_temp", "state": "55", "attributes": {"friendly_name": "Outside Temp"}},
]


def response(status=200, body=None):
    r = mock.Mock(status_code=status, content=b"x" if body is not None else b"")
    r.json.return_value = body
    return r


class HomeAssistantTests(ToolsTestCase):
    cfg = {"ha_url": "http://ha.local:8123/", "ha_token": "secret"}

    def setUp(self):
        super().setUp()
        self.calls = []

        def fake_request(method, url, headers=None, timeout=None, json=None):
            self.calls.append((method, url, json))
            self.assertEqual(headers["Authorization"], "Bearer secret")
            return response(body=STATES if url.endswith("/api/states") else [])

        patcher = mock.patch.object(home_assistant.requests, "request", side_effect=fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def service_calls(self):
        return [(url.split("/api/services/")[1], data) for method, url, data in self.calls if method == "POST"]

    def test_tools_offered_only_when_configured(self):
        self.assertIn("control_device", {s["name"] for s in self.tools.schemas()})

    def test_list_excludes_locks_and_sensors(self):
        devices = json.loads(self.call("list_devices"))
        names = [d["name"] for d in devices]
        self.assertNotIn("Front Door", names)
        self.assertNotIn("Outside Temp", names)
        kitchen = next(d for d in devices if d["name"] == "Kitchen Light")
        self.assertEqual(kitchen["brightness_pct"], 50)
        self.assertEqual(json.loads(self.call("list_devices", kind="thermostats"))[0]["temperature"], 70)

    def test_turn_on_by_spoken_name(self):
        self.assertEqual(self.call("control_device", name="the coffee maker", action="on"), "Coffee Maker turned on.")
        self.assertEqual(self.service_calls(), [("switch/turn_on", {"entity_id": "switch.coffee_maker"})])

    def test_plural_and_brightness(self):
        self.assertEqual(self.call("control_device", name="kitchen lights", action="on", brightness_pct=30),
                         "Kitchen Light set to 30 percent.")
        self.assertEqual(self.service_calls(), [("light/turn_on", {"entity_id": "light.kitchen", "brightness_pct": 30})])

    def test_ambiguous_name_asks(self):
        result = json.loads(self.call("control_device", name="bedroom", action="off"))
        self.assertEqual(sorted(result["several_match"]), ["Bedroom Ceiling", "Bedroom Lamp"])
        self.assertEqual(self.service_calls(), [])

    def test_locks_cannot_be_controlled(self):
        self.assertIn("can't find a light, switch or fan", self.call("control_device", name="front door", action="off"))
        self.assertEqual(self.service_calls(), [])

    def test_close_spelling(self):
        self.assertIn("Bedroom Lamp", self.call("control_device", name="bedrom lamp", action="toggle"))

    def test_thermostat_single_device_no_name(self):
        self.assertEqual(self.call("set_thermostat", temperature=72, mode="heat"),
                         "Hallway Thermostat set to mode heat and 72 degrees.")
        self.assertEqual(self.service_calls(), [
            ("climate/set_hvac_mode", {"entity_id": "climate.hallway", "hvac_mode": "heat"}),
            ("climate/set_temperature", {"entity_id": "climate.hallway", "temperature": 72})])

    def test_errors_are_spoken_plainly(self):
        with mock.patch.object(home_assistant.requests, "request", return_value=response(401)):
            self.assertIn("rejected the access token", self.call("list_devices"))
        with mock.patch.object(home_assistant.requests, "request", side_effect=requests.ConnectionError()):
            self.assertIn("can't reach Home Assistant at http://ha.local:8123", self.call("list_devices"))


class HomeAssistantOffTests(ToolsTestCase):
    def test_hidden_and_explains(self):
        self.assertNotIn("control_device", {s["name"] for s in self.tools.schemas()})
        self.assertIn("isn't set up", self.call("list_devices"))
