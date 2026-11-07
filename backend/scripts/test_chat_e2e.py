"""End-to-end LLM chat test: configure the backend with a *custom OpenAI-compatible*
endpoint pointing at a local mock, then verify parse -> candidate pool ->
constrained re-rank -> explain.

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
RERANK_DOC = {
    "picks": [
        {"id": "sun-kee-curry-house", "reason": "LLM: halal budget curry lunch."}
    ],
    "summary": "The cleanest halal curry fit for a cheap lunch.",
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
        if "<candidates>" in user_text:
            content = json.dumps(RERANK_DOC)
        elif "picks" in user_text:
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

    # 1) save config pointing at the mock
    cfg = put(
        "/api/llm-config",
        {"provider": "custom", "base_url": f"http://{MOCK[0]}:{MOCK[1]}/v1", "model": "mock-model", "api_key": "test"},
    )
    assert cfg["provider"] == "custom", cfg

    # 2) chat -> parse, constrained re-rank, explain
    res = post("/api/chat", {"message": "halal cheap curry lunch please", "limit": 3})
    assert res["mode"] == "llm", res["mode"]
    assert res["structured"]["meal"] == "lunch"
    assert "halal" in res["structured"]["dietary"]
    assert res["selection_mode"] == "llm_rerank", res["selection_mode"]
    assert res["candidate_count"] >= 1, res["candidate_count"]
    ids = [p["id"] for p in res["picks"]]
    assert "sun-kee-curry-house" in ids, ids
    assert ids[0] == "sun-kee-curry-house", ids
    assert "Halal" in res["summary"], res["summary"]
    pick = next(p for p in res["picks"] if p["id"] == "sun-kee-curry-house")
    assert "halal" in pick["reason"].lower(), pick
    print("OK  LLM chat: parsed filters, re-ranked, explained:", ids)

    # 3) config GET reflects saved state
    got = json.loads(urllib.request.urlopen(BASE + "/api/llm-config").read())
    assert got["configured"] is True
    print("OK  llm-config persisted + configured =", got["configured"])

    # 4) demo mode resets selection to deterministic
    put("/api/llm-config", {"provider": "none", "model": "", "base_url": "", "api_key": "", "temperature": 0.3})
    res = post("/api/chat", {"message": "halal cheap curry lunch please", "limit": 3})
    assert res["mode"] == "demo", res["mode"]
    assert res["selection_mode"] == "deterministic", res["selection_mode"]
    assert res["candidate_count"] >= 1, res["candidate_count"]
    print("OK  demo mode stays deterministic:", [p["id"] for p in res["picks"]])

    print("\nE2E LLM chat test passed ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
