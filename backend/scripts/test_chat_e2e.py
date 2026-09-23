"""End-to-end LLM chat test: configure the backend with a *custom OpenAI-compatible*
endpoint pointing at a local mock, then verify parse -> rank -> explain -> memory.

Run: backend/.venv/bin/python backend/scripts/test_chat_e2e.py   (requires backend on :8010)
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import urllib.request

BASE = "http://127.0.0.1:8010"
MOCK = ("127.0.0.1", 8081)

PARSE_DOC = {
    "meal": "lunch",
    "cuisines": ["Indian"],
    "price_level": 1,
    "open_at": None,
    "dietary": ["halal"],
    "keywords": ["curry"],
    "avoid": [],
    "notes": "upper",
}
EXPLAIN_DOC = {
    "summary": "Halal budget lunch: Sun Kee Curry House is the clear winner — fully halal kitchen, $45 student set, 7 min walk.",
    "picks": {"sun-kee-curry-house": "Halal kitchen + $45 lunch set + budget price."},
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        user_text = (body.get("messages") or [{}])[-1].get("content", "")
        if "picks" in user_text:
            content = json.dumps(EXPLAIN_DOC)
        else:
            content = json.dumps(PARSE_DOC)
        payload = {"choices": [{"message": {"content": content}}]}
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def post(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def put(path, payload):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="PUT"
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def main():
    threading.Thread(target=HTTPServer(MOCK, Handler).serve_forever, daemon=True).start()

    # 0) clean slate: clear prior suggestion memory
    req = urllib.request.Request(BASE + "/api/memory/suggestions", method="DELETE")
    urllib.request.urlopen(req).read()

    # 1) save config pointing at the mock
    cfg = put(
        "/api/llm-config",
        {"provider": "custom", "base_url": f"http://{MOCK[0]}:{MOCK[1]}/v1", "model": "mock-model", "api_key": "test"},
    )
    assert cfg["provider"] == "custom", cfg

    # 2) chat -> should use LLM mode
    res = post("/api/chat", {"message": "halal cheap curry lunch please", "limit": 3})
    assert res["mode"] == "llm", res["mode"]
    assert res["structured"]["meal"] == "lunch"
    assert "halal" in res["structured"]["dietary"]
    ids = [p["id"] for p in res["picks"]]
    assert "sun-kee-curry-house" in ids, ids
    assert "Halal" in res["summary"], res["summary"]
    pick = next(p for p in res["picks"] if p["id"] == "sun-kee-curry-house")
    assert "Halal kitchen" in pick["reason"], pick
    print("OK  LLM chat: parsed filters, ranked, explained, memory recorded:", ids)

    # 3) memory now contains the suggestion
    mem = json.loads(urllib.request.urlopen(BASE + "/api/memory").read())
    names = [s["restaurant_name"] for s in mem["suggestions"]]
    assert "Sun Kee Curry House" in names, names
    print("OK  memory recorded:", names)

    # 4) config GET reflects saved state
    got = json.loads(urllib.request.urlopen(BASE + "/api/llm-config").read())
    assert got["configured"] is True
    print("OK  llm-config persisted + configured =", got["configured"])

    # 5) reset to demo mode
    put("/api/llm-config", {"provider": "none", "model": "", "base_url": "", "api_key": "", "temperature": 0.3})
    print("\nE2E LLM chat test passed ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
