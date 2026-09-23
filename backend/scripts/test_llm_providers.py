"""Mock LLM endpoints (OpenAI-compat, Anthropic, Gemini) + provider unit test.

Run: backend/.venv/bin/python backend/scripts/test_llm_providers.py
Starts a local HTTP server, exercises all three provider classes, prints results.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm.providers import (  # noqa: E402
    AnthropicProvider,
    GeminiProvider,
    LLMError,
    OpenAICompatibleProvider,
)

CAPTURED = {}
DOC = '{"meal": "lunch", "cuisines": ["Noodles"], "price_level": 1, "open_at": null, "dietary": [], "keywords": ["noodles"], "avoid": [], "notes": "test"}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        body = self._body()
        CAPTURED["url"] = self.path
        CAPTURED["body"] = body
        CAPTURED["headers"] = dict(self.headers)

        if "/chat/completions" in self.path:
            if body.get("response_format"):
                content = DOC
            else:
                content = "PONG"
            payload = {
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "model": body["model"],
            }
        elif "/v1/messages" in self.path:
            tool_input = json.loads(DOC)
            payload = {
                "content": [
                    {"type": "text", "text": "thinking..."},
                    {"type": "tool_use", "id": "t1", "name": "structured_output", "input": tool_input},
                ],
                "model": body["model"],
            }
        elif ":generateContent" in self.path:
            payload = {
                "candidates": [{"content": {"parts": [{"text": DOC}]}}],
                "modelVersion": body.get("model", ""),
            }
        else:
            payload = {}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    server = HTTPServer(("127.0.0.1", 8077), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:8077"
    schema = {"type": "object", "properties": {"meal": {"type": "string"}}, "required": ["meal"]}
    ok = True

    # 1) OpenAI-compatible (covers OpenAI/DeepSeek/Ollama/custom)
    p = OpenAICompatibleProvider("sk-test", f"{base}/v1", "test-model")
    out = p.chat_json("sys", "hello", schema)
    assert out["meal"] == "lunch" and out["cuisines"] == ["Noodles"], out
    assert CAPTURED["body"]["response_format"] == {"type": "json_object"}, CAPTURED["body"]
    assert CAPTURED["headers"].get("Authorization") == "Bearer sk-test"
    assert p.ping() == "PONG"
    print("OK  OpenAI-compatible: JSON mode, auth header, ping")

    # 2) Anthropic
    p = AnthropicProvider("sk-ant-test", f"{base}", "claude-mock")
    out = p.chat_json("sys", "hello", schema)
    assert out["meal"] == "lunch"
    assert CAPTURED["body"]["tool_choice"] == {"type": "tool", "name": "structured_output"}
    assert CAPTURED["headers"].get("x-api-key") == "sk-ant-test"
    print("OK  Anthropic: tool_use extraction, x-api-key")

    # 3) Gemini
    p = GeminiProvider("gem-key", f"{base}", "gemini-mock")
    out = p.chat_json("sys", "hello", schema)
    assert out["meal"] == "lunch"
    b = CAPTURED["body"]
    assert b["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" in b["generationConfig"]
    assert "?key=gem-key" in CAPTURED["url"]
    print("OK  Gemini: responseSchema + key query param")

    # 4) JSON extraction robustness
    from app.llm.providers import extract_json

    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('prefix {"a": 1} suffix') == {"a": 1}
    print("OK  extract_json: fenced + embedded")

    server.shutdown()
    print("\nAll provider tests passed ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
