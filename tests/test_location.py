import json
from unittest import mock

from jarvis import location
from jarvis.location import Location, Locator

from .helpers import ToolsTestCase

WIN = Location("Baton Rouge, Louisiana", 30.45, -91.15, "Windows location")
IP = Location("New Orleans, Louisiana", 29.95, -90.07, "IP address")


class LocatorTests(ToolsTestCase):
    def locate(self, cfg, win=None, ip=None, win_error=None):
        with mock.patch.object(location, "windows_location", side_effect=win_error, return_value=win) as w, \
             mock.patch.object(location, "ip_location", return_value=ip) as i:
            w.__name__, i.__name__ = "windows_location", "ip_location"
            return Locator(cfg).current(), w, i

    def test_auto_prefers_windows(self):
        loc, _, ip = self.locate({}, win=WIN, ip=IP)
        self.assertEqual(loc, WIN)
        ip.assert_not_called()

    def test_auto_falls_back_to_ip_when_windows_fails(self):
        loc, _, _ = self.locate({}, win_error=OSError("no powershell"), ip=IP)
        self.assertEqual(loc.source, "IP address")

    def test_falls_back_to_home_city(self):
        loc, _, _ = self.locate({"home_city": "Austin"}, win=None, ip=None)
        self.assertEqual((loc.name, loc.lat, loc.source), ("Austin", None, "home city"))

    def test_ip_mode_skips_windows(self):
        loc, win, _ = self.locate({"location_mode": "ip"}, ip=IP)
        win.assert_not_called()
        self.assertEqual(loc, IP)

    def test_home_mode_uses_no_network(self):
        loc, win, ip = self.locate({"location_mode": "home", "home_city": "Austin"}, win=WIN, ip=IP)
        win.assert_not_called()
        ip.assert_not_called()
        self.assertEqual(loc.source, "home city")

    def test_result_is_cached(self):
        locator = Locator({})
        with mock.patch.object(location, "windows_location", return_value=WIN) as w:
            locator.current()
            locator.current()
        self.assertEqual(w.call_count, 1)

    def test_nothing_known(self):
        loc, _, _ = self.locate({"location_mode": "home"})
        self.assertEqual(loc.name, "")


class LocationToolTests(ToolsTestCase):
    def test_get_location_tool(self):
        self.tools.locator.current = lambda: IP
        self.assertEqual(json.loads(self.call("get_location")), {"place": "New Orleans, Louisiana",
                                                                 "based_on": "IP address"})
        self.tools.locator.current = lambda: Location("", source="unknown")
        self.assertIn("home city in settings", self.call("get_location"))

    def test_weather_without_place_uses_coordinates(self):
        self.tools.locator.current = lambda: WIN
        with mock.patch.object(self.tools, "_weather_at", return_value={"ok": 1}) as wx:
            self.call("get_weather")
        wx.assert_called_once_with(30.45, -91.15, "Baton Rouge, Louisiana")

    def test_weather_with_home_city_only_geocodes_it(self):
        self.tools.locator.current = lambda: Location("Austin", source="home city")
        fake_geo = mock.Mock()
        fake_geo.json.return_value = {"results": [{"name": "Austin", "admin1": "Texas",
                                                   "latitude": 30.27, "longitude": -97.74}]}
        with mock.patch("jarvis.tools.requests.get", return_value=fake_geo), \
             mock.patch.object(self.tools, "_weather_at", return_value={"ok": 1}) as wx:
            self.call("get_weather")
        wx.assert_called_once_with(30.27, -97.74, "Austin, Texas")

    def test_weather_named_place_ignores_location(self):
        self.tools.locator.current = mock.Mock(side_effect=AssertionError("shouldn't look up location"))
        fake_geo = mock.Mock()
        fake_geo.json.return_value = {"results": [{"name": "Paris", "admin1": "Ile-de-France",
                                                   "latitude": 48.85, "longitude": 2.35}]}
        with mock.patch("jarvis.tools.requests.get", return_value=fake_geo), \
             mock.patch.object(self.tools, "_weather_at", return_value={"ok": 1}):
            self.assertEqual(json.loads(self.call("get_weather", location="Paris")), {"ok": 1})
