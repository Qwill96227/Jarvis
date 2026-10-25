import json
import os
import unittest
from pathlib import Path
from unittest import mock

from jarvis import system_tools
from jarvis.system_tools import inside_home, parse_netsh, process_name, search

from .helpers import ToolsTestCase

NETSH_CONNECTED = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    State                  : connected
    SSID                   : HomeNet
    BSSID                  : aa:bb:cc:dd:ee:ff
    Signal                 : 87%
"""
NETSH_PROFILES = """
User profiles
-------------
    All User Profile     : HomeNet
    All User Profile     : Coffee Shop
"""


class HelperTests(unittest.TestCase):
    def test_process_names(self):
        self.assertEqual(process_name("Chrome"), "chrome.exe")
        self.assertEqual(process_name("VS Code"), "code.exe")
        self.assertEqual(process_name("obs studio"), "obsstudio.exe")
        self.assertEqual(process_name("notepad.exe"), "notepad.exe")

    def test_parse_netsh(self):
        info = parse_netsh(NETSH_CONNECTED)
        self.assertEqual((info["state"], info["ssid"], info["signal"]), ("connected", "HomeNet", "87%"))


class FileToolTests(ToolsTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        for rel in ["Documents/Resume 2026.pdf", "Documents/notes.txt", "Downloads/resume_old.docx",
                    "Downloads/setup.exe", "AppData/Local/resume_cache.pdf", ".hidden/resume.pdf"]:
            (self.home / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.home / rel).write_text("x")
        folders = {"home": self.home, "documents": self.home / "Documents", "downloads": self.home / "Downloads"}
        self.patches = [mock.patch.object(system_tools, "HOME", self.home),
                        mock.patch.dict(system_tools.FOLDERS, folders, clear=True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def test_search_substring_skips_appdata_and_hidden(self):
        names = sorted(p.name for p in search("resume", [self.home]))
        self.assertEqual(names, ["Resume 2026.pdf", "resume_old.docx"])

    def test_search_wildcard_and_tool_output(self):
        rows = json.loads(self.call("search_files", name="*.pdf", folder="documents"))
        self.assertEqual([r["name"] for r in rows], ["Resume 2026.pdf"])
        self.assertIn("No files", self.call("search_files", name="taxes"))

    def test_paths_outside_home_refused(self):
        with self.assertRaises(ValueError):
            inside_home(self.tmp / "elsewhere.txt", root=self.home)
        self.assertIn("only work with files in your user folders",
                      self.call("open_file", path=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "notepad.exe")))

    def test_open_file_refuses_programs(self):
        with mock.patch.object(os, "startfile", create=True) as start:
            self.assertIn("safety rule", self.call("open_file", path=str(self.home / "Downloads/setup.exe")))
            start.assert_not_called()
            self.assertIn("Opening notes.txt", self.call("open_file", path=str(self.home / "Documents/notes.txt")))
            start.assert_called_once()

    def test_move_file_and_no_overwrite(self):
        reply = self.call("move_file", path=str(self.home / "Downloads/resume_old.docx"), to_folder="documents")
        self.assertEqual(reply, "Moved resume_old.docx to Documents.")
        self.assertTrue((self.home / "Documents/resume_old.docx").exists())
        (self.home / "Downloads/notes.txt").write_text("other")
        self.assertIn("already a notes.txt", self.call("move_file", path=str(self.home / "Downloads/notes.txt"),
                                                       to_folder="documents"))
        self.assertEqual((self.home / "Documents/notes.txt").read_text(), "x")  # untouched


class AppAndDeviceTests(ToolsTestCase):
    def test_protected_processes(self):
        self.assertIn("won't close", self.call("close_app", name="explorer"))

    def test_close_app_is_polite(self):
        fake_proc = mock.Mock(info={"name": "Spotify.exe"})
        with mock.patch.object(system_tools.psutil, "process_iter", return_value=[fake_proc]), \
             mock.patch.object(system_tools, "_run", return_value="SUCCESS: sent termination signal") as run:
            self.assertEqual(self.call("close_app", name="spotify"), "Closing spotify.")
            self.assertEqual(run.call_args.args[0], ["taskkill", "/IM", "spotify.exe"])  # no /F

    def test_close_app_not_running(self):
        with mock.patch.object(system_tools.psutil, "process_iter", return_value=[]):
            self.assertIn("isn't running", self.call("close_app", name="discord"))

    def test_wifi(self):
        with mock.patch.object(system_tools, "_run", return_value="The Wireless AutoConfig Service (wlansvc) is not running."):
            self.assertIn("isn't using Wi-Fi", self.call("wifi_control", action="status"))
        with mock.patch.object(system_tools, "_run", side_effect=[NETSH_CONNECTED]):
            self.assertEqual(json.loads(self.call("wifi_control", action="status")),
                             {"network": "HomeNet", "signal": "87%"})
        with mock.patch.object(system_tools, "_run", side_effect=[NETSH_CONNECTED, NETSH_PROFILES]):
            self.assertEqual(json.loads(self.call("wifi_control", action="list")), ["HomeNet", "Coffee Shop"])
        with mock.patch.object(system_tools, "_run", side_effect=[NETSH_CONNECTED, "There is no profile"]):
            self.assertIn("joined before", self.call("wifi_control", action="connect", network="Airport"))

    def test_brightness(self):
        with mock.patch.object(system_tools, "_powershell", return_value=""):
            self.assertIn("external monitor", self.call("set_brightness", level=50))
        with mock.patch.object(system_tools, "_powershell", side_effect=["90", ""]) as ps:
            self.assertEqual(self.call("set_brightness", change=30), "Brightness set to 100 percent.")
            self.assertIn("Brightness=100", ps.call_args.args[0])

    @unittest.skipUnless(os.name == "nt", "Windows only")
    def test_list_windows_on_this_pc(self):
        result = self.call("list_windows")
        rows = json.loads(result) if result.startswith("[") else []
        self.assertTrue(all({"app", "title"} <= r.keys() for r in rows))
