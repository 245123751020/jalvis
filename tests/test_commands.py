"""Unit tests for the JARVIS command engine and app index.
Desktop actions (launching apps, volume, power) are mocked so the suite
never opens applications or changes machine state.
"""
import subprocess
import unittest
from unittest import mock

from apps_index import AppIndex
from commands import HELP, CommandEngine


class AppIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = AppIndex()

    def test_discovers_installed_apps(self):
        self.assertGreater(len(self.index.apps), 0)
        names = " ".join(a.name.casefold() for a in self.index.apps)
        self.assertIn("firefox", names)
        self.assertIn("calculator", names)

    def test_aliases_resolve(self):
        self.assertEqual(self.index.find("calc").name, "Calculator")
        self.assertEqual(self.index.find("gnome terminal").name, "Terminal")
        self.assertEqual(self.index.find("nautilus").name, "Files")
        chrome = self.index.find("chrome")
        self.assertIsNotNone(chrome)
        self.assertIn("chrome", chrome.name.casefold())

    def test_unknown_returns_none(self):
        self.assertIsNone(self.index.find("totally-not-an-app"))

    def test_suggestions(self):
        self.assertIn("Calculator", self.index.suggest("calc"))
        self.assertIn("Firefox", self.index.suggest("firefox"))


class WebUrlTests(unittest.TestCase):
    def check(self, target, expected):
        engine = CommandEngine(index=AppIndex())
        self.assertEqual(engine.web_url(target), expected)

    def test_valid_urls(self):
        self.check("example.com", "https://example.com")
        self.check("www.example.com/path?q=1", "https://www.example.com/path?q=1")
        self.check("https://sub.example.org:8443/x", "https://sub.example.org:8443/x")
        self.check("localhost:8080", "https://localhost:8080")
        self.check("http://example.com", "http://example.com")

    def test_invalid_urls(self):
        self.check("not a url", None)
        self.check("javascript:alert(1)", None)
        self.check("ftp://example.com", None)
        self.check("https://", None)
        self.check("user@example.com", None)
        self.check("example", None)


class CommandEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = CommandEngine(index=AppIndex())
        self.process = mock.Mock()
        self.process.wait.return_value = 0
        self.process.returncode = 0
        self.popen = mock.Mock(return_value=self.process)
        self.run = mock.Mock(return_value=self.process)
        self._pp = mock.patch.object(subprocess, "Popen", self.popen)
        self._rr = mock.patch.object(subprocess, "run", self.run)
        self._pp.start()
        self._rr.start()
        self.addCleanup(self._pp.stop)
        self.addCleanup(self._rr.stop)

    def execute(self, text):
        return self.engine.execute(text)

    def test_hello_shows_help(self):
        self.assertIn("open firefox", self.execute("hey").text)

    def test_time_and_date(self):
        self.assertRegex(self.execute("time").text, r"It's .+ [AP]M\.")
        self.assertIn("Today is", self.execute("date").text)

    def test_apps_lists_index(self):
        self.assertIn("Firefox", self.execute("apps").text)

    def test_search_makes_google_query(self):
        self.execute("search python tutorial")
        url = self.popen.call_args[0][0][1]
        self.assertIn("https://www.google.com/search?q=", url)
        self.assertIn("python+tutorial", url)

    def test_search_youtube(self):
        self.execute("search youtube for cats")
        url = self.popen.call_args[0][0][1]
        self.assertIn("https://www.youtube.com/results?search_query=cats", url)

    def test_open_site_and_url(self):
        self.assertIn("youtube", self.execute("open youtube").text)
        self.assertIn("in your browser", self.execute("open example.com").text)

    def test_open_app_uses_gio_launch(self):
        firefox = next(a.path for a in self.engine.index.apps if a.name == "Firefox")
        self.assertIn("Firefox", self.execute("open firefox").text)
        argv = self.popen.call_args[0][0]
        self.assertEqual(argv, ["/usr/bin/gio", "launch", str(firefox)])

    def test_open_folder(self):
        self.execute("open downloads")
        self.assertEqual(self.popen.call_args[0][0][0], "/usr/bin/xdg-open")

    def test_unknown_app_is_never_launched(self):
        result = self.execute("open totally-not-an-app")
        self.assertIn("couldn't find", result.text)
        self.assertEqual(self.popen.call_count, 0)
        self.assertEqual(self.run.call_count, 0)

    def test_javascript_url_never_launched(self):
        result = self.execute("open javascript:alert(1)")
        self.assertIn("couldn't find", result.text)
        self.assertEqual(self.popen.call_count, 0)
        self.assertEqual(self.run.call_count, 0)

    def test_volume_commands(self):
        self.assertEqual(self.execute("volume up").text, "Volume updated.")
        self.assertEqual(self.execute("mute").text, "Volume updated.")
        self.assertEqual(self.run.call_count, 2)
        self.assertEqual(
            self.run.call_args_list[0][0][0],
            ["/usr/bin/pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
        )

    def test_lock(self):
        self.assertEqual(self.execute("lock").text, "Screen lock requested.")
        self.assertEqual(self.run.call_args[0][0], ["/usr/bin/loginctl", "lock-session"])

    def test_unknown_command(self):
        self.assertIn("don't recognize", self.execute("dance").text)

    def test_shutdown_needs_confirmation(self):
        result = self.execute("shutdown")
        self.assertEqual(result.confirm, "shutdown")
        self.assertEqual(self.popen.call_count, 0)
        self.assertEqual(self.run.call_count, 0)

    def test_confirm_shutdown_powers_off(self):
        result = self.engine.confirm_action("shutdown")
        self.assertIn("Powering off", result.text)
        self.assertEqual(self.run.call_args[0][0], ["/usr/bin/systemctl", "poweroff"])


if __name__ == "__main__":
    unittest.main()
