"""Tests for the LLM conversation worker and the close command.

The Groq network calls are replaced by a fake client so nothing external runs.
"""
import subprocess
import unittest
from unittest import mock

from PyQt5.QtCore import QCoreApplication

import jarvis
from commands import CommandEngine
from apps_index import AppIndex
from jarvis import ACTION_INTENT_RE, LLMWorker


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat(self, messages, **kwargs):
        return self.responses.pop(0)


def tool_response(command):
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "run_action", "arguments": f'{{"command": "{command}"}}'},
                }],
            }
        }]
    }


def plain_response(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


class LLMWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication([])

    def test_clean_strips_tool_markup(self):
        dirty = "YouTube is open.\n\n<tool_call>\n<function=run_action>\n<parameter=command>search youtube for x</parameter>\n</function>\n</tool_call>\n\nEnjoy!"
        self.assertNotIn("tool_call", LLMWorker.clean(dirty))
        self.assertNotIn("run_action", LLMWorker.clean(dirty))

    def test_force_action_matches_intents(self):
        for phrase in ("open chatgpt", "close the chrome", "search cats", "volume up",
                       "what time is it", "lock the screen", "open youtube and search spiderman"):
            self.assertTrue(ACTION_INTENT_RE.search(phrase), phrase)
        for phrase in ("tell me a joke", "thanks!", "hello"):
            self.assertFalse(ACTION_INTENT_RE.search(phrase), phrase)

    def test_multi_action_loop_executes_all_tools(self):
        client = FakeClient([
            tool_response("time"),
            plain_response("Done — that's the answer."),
        ])
        engine = CommandEngine(index=AppIndex())
        messages = [{"role": "user", "content": "what time is it"}]
        worker = LLMWorker(client, engine, messages, "fake-model", force_action=True)
        replies, commands, failures = [], [], []

        def on_action(command, text):
            commands.append(command)

        worker.reply.connect(replies.append)
        worker.action_done.connect(on_action)
        worker.failed.connect(failures.append)
        worker.run()

        self.assertEqual(commands, ["time"])
        self.assertEqual(len(replies), 1)
        self.assertFalse(failures)
        self.assertEqual(replies[0], "Done — that's the answer.")

    def test_multi_call_in_one_message(self):
        client = FakeClient([
            tool_response("time"),
            tool_response("date"),
            plain_response("Here you go."),
        ])
        engine = CommandEngine(index=AppIndex())
        worker = LLMWorker(client, engine, [], "fake-model", force_action=True)
        replies, actions = [], []

        def on_action(command, text):
            actions.append(command)

        worker.reply.connect(replies.append)
        worker.action_done.connect(on_action)
        worker.run()

        self.assertEqual(actions, ["time", "date"])
        self.assertEqual(replies, ["Here you go."])


class CloseCommandTests(unittest.TestCase):
    def setUp(self):
        self.engine = CommandEngine(index=AppIndex())

    def test_close_chrome_running(self):
        run = mock.Mock()
        run.return_value.returncode = 0
        with mock.patch.object(subprocess, "run", run):
            result = self.engine.execute("close chrome")
        self.assertIn("closing chrome", result.text)
        args = run.call_args[0][0]
        self.assertEqual(args[:3], ["pkill", "-TERM", "-x"])

    def test_close_not_running(self):
        run = mock.Mock()
        run.return_value.returncode = 1
        with mock.patch.object(subprocess, "run", run):
            result = self.engine.execute("close chrome")
        self.assertIn("didn't appear to be running", result.text)

    def test_close_unknown_app(self):
        result = self.engine.execute("close someweirdapp123")
        self.assertIn("safe way", result.text)


if __name__ == "__main__":
    unittest.main()