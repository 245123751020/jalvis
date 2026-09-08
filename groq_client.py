"""Minimal Groq API client for chat and model discovery (stdlib only).

The API key is read from the GROQ_API_KEY environment variable, falling back
to ~/.config/jarvis/groq_key. The key is never stored in source code.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


API_URL = "https://api.groq.com/openai/v1"
CHAT_URL = API_URL + "/chat/completions"
MODELS_URL = API_URL + "/models"

DEFAULT_MODEL = "qwen/qwen3.8-27b"
PREFERRED_MODELS = (
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "groq/compound-mini",
    "openai/gpt-oss-120b",
    "groq/compound",
)
_NON_CHAT_TAGS = ("whisper", "prompt-guard", "allam", "orpheus")

# OpenAI-style function-calling schema used to bind desktop actions.
RUN_ACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "run_action",
        "description": (
            "Ask the local system to perform an action such as opening an app, "
            "website, folder, running a search, or changing system settings. "
            "Use only commands from the list provided in the system prompt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact command to run, e.g. 'open firefox' or 'search cats'.",
                }
            },
            "required": ["command"],
        },
    },
}


class GroqError(Exception):
    pass


class GroqClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY") or self._read_key_file()
        self._models = None

    @staticmethod
    def _read_key_file():
        path = Path.home() / ".config" / "jarvis" / "groq_key"
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    @property
    def available(self):
        return bool(self.api_key)

    def _request_json(self, url, payload=None, timeout=60):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, method="POST" if body else "GET")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        # Groq's edge layer rejects the stock Python User-Agent (HTTP 403),
        # so present an ordinary browser identity.
        request.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) JARVIS/1.0")
        if body:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise GroqError(f"Groq API HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise GroqError(f"Groq connection error: {error}") from error

    def fetch_models(self):
        if self._models is None:
            self._models = self._request_json(MODELS_URL, timeout=20)
        return self._models

    def available_models(self):
        return [m.get("id") for m in self.fetch_models().get("data", []) if m.get("active")]

    def pick_model(self, preferred=None):
        available = self.available_models()
        for model in preferred or PREFERRED_MODELS:
            if model in available:
                return model
        for model in available:
            if not any(tag in model.casefold() for tag in _NON_CHAT_TAGS):
                return model
        return available[0] if available else DEFAULT_MODEL

    def chat(self, messages, *, model=None, tools=None, tool_choice=None,
             temperature=0.4, max_tokens=450, timeout=90):
        payload = {
            "model": model or DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        elif tool_choice:
            payload["tool_choice"] = tool_choice
        return self._request_json(CHAT_URL, payload, timeout=timeout)