"""LLM provider layer. Implements a common chat-with-JSON interface over raw HTTP
(httpx) so every provider works without provider SDKs:

- OpenAI, DeepSeek, Ollama, LM Studio, vLLM... -> OpenAI-compatible /chat/completions
- Anthropic Claude                            -> /v1/messages  (forced tool_use = JSON)
- Google Gemini                               -> :generateContent (responseSchema)

A config with provider=="none" (or missing model) means "no LLM": callers fall
back to a deterministic keyword parser (demo mode).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "ollama": "http://localhost:11434/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}

PROVIDER_INFO = {
    "none": {"label": "No LLM (demo mode)", "default_base": "", "default_model": "", "needs_key": False},
    "openai": {"label": "OpenAI", "default_base": DEFAULT_BASE_URLS["openai"], "default_model": "gpt-4o-mini", "needs_key": True},
    "deepseek": {"label": "DeepSeek", "default_base": DEFAULT_BASE_URLS["deepseek"], "default_model": "deepseek-chat", "needs_key": True},
    "anthropic": {"label": "Anthropic Claude", "default_base": DEFAULT_BASE_URLS["anthropic"], "default_model": "claude-3-5-sonnet-latest", "needs_key": True},
    "gemini": {"label": "Google Gemini", "default_base": DEFAULT_BASE_URLS["gemini"], "default_model": "gemini-2.0-flash", "needs_key": True},
    "ollama": {"label": "Ollama / LM Studio (local)", "default_base": DEFAULT_BASE_URLS["ollama"], "default_model": "llama3.1", "needs_key": False},
    "custom": {"label": "Custom OpenAI-compatible endpoint", "default_base": "", "default_model": "", "needs_key": False},
}


class LLMError(Exception):
    """Raised when a provider request fails (network/auth/parse)."""


def extract_json(text: str) -> dict:
    """Robust JSON extraction: direct parse, then first balanced {...} block."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise LLMError("No JSON object found in model response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    raise LLMError(f"Failed to parse model JSON: {e}") from e
    raise LLMError("Unbalanced JSON in model response")


def _gemini_schema(schema: dict) -> dict:
    """Convert a strict JSON Schema (subset) to Gemini's OpenAPI-style schema."""
    allowed = {"type", "properties", "required", "items", "enum", "description"}

    def conv(s: dict) -> dict:
        out: dict[str, Any] = {}
        for k, v in s.items():
            if k not in allowed or v is None:
                continue
            if k == "type" and isinstance(v, str):
                out["type"] = v
            elif k == "properties" and isinstance(v, dict):
                out["properties"] = {pk: conv(pv) for pk, pv in v.items()}
            elif k == "items" and isinstance(v, dict):
                out["items"] = conv(v)
            else:
                out[k] = v
        if out.get("type") == "object":
            # Gemini: object schemas must be closed by default
            out.setdefault("required", list((s.get("properties") or {}).keys()))
        return out

    return conv(schema)


class BaseProvider:
    name = "base"

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.3):
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.temperature = temperature

    def chat_json(self, system: str, user: str, schema: dict, max_tokens: int = 1024) -> dict:
        raise NotImplementedError

    def ping(self, max_tokens: int = 16) -> str:
        raise NotImplementedError


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI / DeepSeek / Ollama / LM Studio / vLLM / any /v1 compatible server."""

    def _post(self, payload: dict, extra_headers: Optional[dict] = None, timeout: float = 90.0) -> httpx.Response:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra_headers:
            headers.update(extra_headers)
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise LLMError(f"Network error reaching {self.base_url}: {e}") from e
        return resp

    def chat_json(self, system: str, user: str, schema: dict, max_tokens: int = 1024) -> dict:
        base_payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        # Try JSON-object mode first; fall back if endpoint rejects it.
        last_error: Optional[Exception] = None
        for use_json_mode in (True, False):
            payload = dict(base_payload)
            if use_json_mode:
                payload["response_format"] = {"type": "json_object"}
            resp = self._post(payload)
            if resp.status_code in (400, 404, 422) and use_json_mode:
                last_error = LLMError(f"Endpoint rejected JSON mode ({resp.status_code}): {resp.text[:300]}")
                continue
            if resp.status_code != 200:
                raise LLMError(f"Provider error {resp.status_code}: {resp.text[:400]}")
            data = resp.json()
            try:
                content = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError(f"Unexpected response shape: {str(data)[:300]}") from e
            return extract_json(content)
        raise last_error or LLMError("Unknown error")

    def ping(self, max_tokens: int = 16) -> str:
        resp = self._post(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
                "max_tokens": max_tokens,
                "temperature": 0,
            }
        )
        if resp.status_code != 200:
            raise LLMError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class AnthropicProvider(BaseProvider):
    def _headers(self):
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _call(self, payload: dict) -> httpx.Response:
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(f"{self.base_url}/v1/messages", json=payload, headers=self._headers())
        except httpx.HTTPError as e:
            raise LLMError(f"Network error reaching {self.base_url}: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"Anthropic error {resp.status_code}: {resp.text[:400]}")
        return resp

    def chat_json(self, system: str, user: str, schema: dict, max_tokens: int = 1024) -> dict:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": "structured_output",
                    "description": "Emit the structured result requested by the user.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": "structured_output"},
        }
        resp = self._call(payload)
        data = resp.json()
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return block.get("input", {})
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return extract_json(text)

    def ping(self, max_tokens: int = 16) -> str:
        resp = self._call(
            {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
            }
        )
        data = resp.json()
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return text.strip() or "PONG"


class GeminiProvider(BaseProvider):
    def _call(self, payload: dict, model: Optional[str] = None) -> httpx.Response:
        url = f"{self.base_url}/models/{model or self.model}:generateContent?key={self.api_key}"
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise LLMError(f"Network error reaching {self.base_url}: {e}") from e
        if resp.status_code != 200:
            raise LLMError(f"Gemini error {resp.status_code}: {resp.text[:400]}")
        return resp

    def chat_json(self, system: str, user: str, schema: dict, max_tokens: int = 1024) -> dict:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
                "responseSchema": _gemini_schema(schema),
            },
        }
        resp = self._call(payload)
        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"Unexpected Gemini response: {str(data)[:300]}") from e
        return extract_json(text)

    def ping(self, max_tokens: int = 16) -> str:
        resp = self._call(
            {
                "contents": [{"role": "user", "parts": [{"text": "Reply with exactly: PONG"}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
            }
        )
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def get_provider(config: dict) -> Optional[BaseProvider]:
    """Build a provider from a llm_config row, or None when no LLM is configured."""
    provider = (config.get("provider") or "none").strip()
    model = (config.get("model") or "").strip()
    if provider == "none" or not model:
        return None
    api_key = (config.get("api_key") or "").strip()
    base_url = (config.get("base_url") or "").strip() or DEFAULT_BASE_URLS.get(provider, "")
    temperature = float(config.get("temperature") or 0.3)

    if provider in ("openai", "deepseek", "ollama", "custom"):
        return OpenAICompatibleProvider(api_key, base_url, model, temperature)
    if provider == "anthropic":
        return AnthropicProvider(api_key, base_url, model, temperature)
    if provider == "gemini":
        return GeminiProvider(api_key, base_url, model, temperature)
    return None
