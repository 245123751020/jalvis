"""Offline tests for the Groq client (network is mocked)."""
import json
import os
import unittest
from unittest import mock

import urllib.error

from groq_client import GroqClient, GroqError, RUN_ACTION_TOOL


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class GroqClientTests(unittest.TestCase):
    def setUp(self):
        os.environ["GROQ_API_KEY"] = "test-key"

    def tearDown(self):
        os.environ.pop("GROQ_API_KEY", None)

    def make_client(self):
        return GroqClient(api_key="test-key")

    def test_available_requires_key(self):
        client = self.make_client()
        self.assertTrue(client.available)
        client.api_key = ""
        self.assertFalse(client.available)

    def test_run_action_tool_schema(self):
        self.assertEqual(RUN_ACTION_TOOL["type"], "function")
        self.assertEqual(RUN_ACTION_TOOL["function"]["name"], "run_action")
        self.assertIn("command", RUN_ACTION_TOOL["function"]["parameters"]["properties"])

    def test_pick_model_prefers_available(self):
        client = self.make_client()
        models = {"data": [
            {"id": "whisper-large-v3", "active": True},
            {"id": "qwen/qwen3.8-27b", "active": True},
            {"id": "openai/gpt-oss-20b", "active": True},
        ]}
        client._models = models
        self.assertEqual(client.pick_model(), "qwen/qwen3.8-27b")

    def test_pick_model_filters_non_chat(self):
        client = self.make_client()
        models = {"data": [
            {"id": "whisper-large-v3", "active": True},
            {"id": "allam-2-7b", "active": True},
        ]}
        client._models = models
        self.assertEqual(client.pick_model(), "whisper-large-v3")

    def test_chat_sends_expected_request(self):
        client = self.make_client()
        response = {"choices": [{"message": {"role": "assistant", "content": "hi"}}]}
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(response)) as urlopen:
            result = client.chat(
                [{"role": "user", "content": "hello"}],
                model="m", tools=[RUN_ACTION_TOOL], tool_choice="auto",
            )
        self.assertEqual(result, response)
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertIn("tools", json.loads(request.data.decode()))

    def test_http_error_raises_groq_error(self):
        client = self.make_client()
        import io
        http_error = urllib.error.HTTPError("url", 401, "Unauthorized", None, io.BytesIO(b"bad key"))
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaises(GroqError) as ctx:
                client.chat([{"role": "user", "content": "x"}], model="m")
        self.assertIn("401", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
