import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest import mock

import anthropic
import httpx2 as httpx
import requests

from jarvis.brain import Brain
from jarvis.safety import describe, parse_yes_no

from .helpers import ToolsTestCase


def text(t):
    return SimpleNamespace(type="text", text=t)


def tool(name, id, **inp):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=inp)


def reply(*blocks, stop="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop)


class ScriptedClaude:
    """Stands in for the Anthropic client: returns scripted responses (or raises) in order."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    @contextmanager
    def _stream(self, **kwargs):
        self.requests.append([dict(m) if isinstance(m, dict) else m for m in kwargs["messages"]])
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        yield SimpleNamespace(get_final_message=lambda: step)


def connection_error():
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))


class YesNoTests(unittest.TestCase):
    def test_answers(self):
        for t in ("Yes", "yeah go ahead", "Sure, send it.", "ok", "do it"):
            self.assertIs(parse_yes_no(t), True, t)
        for t in ("No", "nope", "cancel that", "don't send it", "wait, never mind"):
            self.assertIs(parse_yes_no(t), False, t)
        for t in ("", "hmm", "what did it say?", "no, yes, send it"):
            self.assertIsNone(parse_yes_no(t), t)

    def test_descriptions(self):
        q, d = describe("clear_notes", {})
        self.assertEqual(q, "Delete all your notes?")
        self.assertIn("can't be undone", d)


class GateTests(ToolsTestCase):
    def test_irreversible_tool_needs_a_yes(self):
        self.call("save_note", text="buy milk")
        self.assertIn("did not confirm", self.call("clear_notes"))  # no way to ask = no
        self.tools.confirm = lambda q, d: False
        self.assertIn("did not confirm", self.call("clear_notes"))
        self.assertNotEqual(self.call("read_notes"), "No notes saved.")  # still there
        self.tools.confirm = lambda q, d: True
        self.assertEqual(self.call("clear_notes"), "All notes deleted.")

    def test_confirm_list_is_configurable(self):
        self.tools.cfg["confirm_tools"] = ["save_note"]
        self.assertIn("did not confirm", self.call("save_note", text="x"))
        self.tools.confirm = None
        self.assertFalse(self.tools.needs_confirmation("clear_notes"))

    def test_read_only_tools_retry_once_on_network_errors(self):
        calls = []

        def flaky(location=""):
            calls.append(1)
            if len(calls) == 1:
                raise requests.ConnectionError("blip")
            return "sunny"

        with mock.patch.object(self.tools, "t_get_weather", side_effect=flaky), mock.patch("jarvis.tools.time.sleep"):
            self.assertEqual(self.tools.run("get_weather", {}), ("sunny", False))
        self.assertEqual(len(calls), 2)

    def test_actions_are_not_retried(self):
        with mock.patch.object(self.tools, "t_open_website", side_effect=requests.ConnectionError("x")) as fn:
            content, is_error = self.tools.run("open_website", {"url": "x.com"})
        self.assertTrue(is_error)
        self.assertIn("network problem", content)
        self.assertEqual(fn.call_count, 1)

    def test_errors_are_flagged(self):
        self.assertEqual(self.tools.run("no_such_tool", {}), ("Unknown tool: no_such_tool", True))


def confirm_app(voice_turn=False, click=None, voice_reply=None):
    """JarvisApp without its window: the dialog 'clicks' click (or nothing), the mic 'hears' voice_reply."""
    from jarvis.app import JarvisApp
    app = JarvisApp.__new__(JarvisApp)
    app.cfg, app._voice_turn, app.confirming, app.wake = {}, voice_turn, False, None
    app.CONFIRM_TIMEOUT = 0.3
    app.ui = lambda fn, *a: fn(*a)
    app._set_state = mock.Mock()
    app._close_confirm = mock.Mock()
    app._say = mock.Mock()
    app._show_confirm = lambda q, d, answer: click is not None and answer(click)
    app._listen_yes_no = lambda answer, heard: voice_reply is not None and answer(voice_reply)
    return app


class ConfirmFlowTests(unittest.TestCase):
    def test_typed_request_uses_the_dialog(self):
        app = confirm_app(click=True)
        self.assertTrue(app._confirm("Delete all your notes?", "..."))
        app._say.assert_not_called()

    def test_spoken_request_asks_out_loud_and_accepts_a_spoken_yes(self):
        app = confirm_app(voice_turn=True, voice_reply=True)
        self.assertTrue(app._confirm("Send this email to ana@example.com?", "..."))
        app._say.assert_called_once_with("Send this email to ana@example.com? Say yes or no.")

    def test_no_answer_means_no(self):
        app = confirm_app()
        self.assertFalse(app._confirm("Delete all your notes?", "..."))
        self.assertFalse(app.confirming)
        app._close_confirm.assert_called_once()


class MultiStepTests(ToolsTestCase):
    def brain(self, *steps):
        b = Brain({"api_key": "test", "model": "claude-haiku-5-5", "web_search": False}, self.tools)
        b.client = ScriptedClaude(*steps)
        return b

    def test_chains_several_tools_in_one_request(self):
        b = self.brain(
            reply(tool("save_note", "t1", text="buy milk"), stop="tool_use"),
            reply(tool("set_timer", "t2", seconds=600, label="laundry"), stop="tool_use"),
            reply(text("Noted, and your laundry timer is running.")))
        self.assertEqual(b.ask("Note buy milk and set a 10 minute laundry timer"),
                         "Noted, and your laundry timer is running.")
        self.assertEqual(len(self.tools.timers), 1)
        self.assertIn("buy milk", self.call("read_notes"))

    def test_tool_errors_are_flagged_to_claude(self):
        b = self.brain(reply(tool("no_such_tool", "t1"), stop="tool_use"), reply(text("Sorry, I can't.")))
        b.ask("do the impossible")
        result = b.client.requests[1][-1]["content"][0]
        self.assertTrue(result["is_error"])

    def test_declined_confirmation_reaches_claude_as_error(self):
        self.tools.confirm = lambda q, d: False
        b = self.brain(reply(tool("clear_notes", "t1"), stop="tool_use"), reply(text("OK, I left them.")))
        self.assertEqual(b.ask("clear my notes"), "OK, I left them.")
        result = b.client.requests[1][-1]["content"][0]
        self.assertTrue(result["is_error"])
        self.assertIn("did not confirm", result["content"])

    def test_connection_lost_midway_reports_what_was_done_and_keeps_history(self):
        b = self.brain(reply(tool("set_timer", "t1", seconds=60, label="tea"), stop="tool_use"), connection_error())
        answer = b.ask("start a tea timer then check the weather")
        self.assertEqual(answer, "I lost my internet connection. Before that, I'd started the timer.")
        self.assertEqual(b.history[-1]["content"][0]["type"], "tool_result")  # kept, so no re-run next time

    def test_connection_lost_before_anything_rolls_back(self):
        b = self.brain(connection_error())
        self.assertEqual(b.ask("hello"), "I lost my internet connection.")
        self.assertEqual(b.history, [])

    def test_step_limit(self):
        b = self.brain(*[reply(tool("get_datetime", f"t{i}"), stop="tool_use") for i in range(3)])
        b.cfg["max_tool_steps"] = 3
        self.assertIn("as far as I can go", b.ask("loop forever"))
