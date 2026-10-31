"""M1 regression: infeasible requests must refuse explicitly (or disclose
relaxation), never silently relax constraints.

Run: backend/.venv/bin/python backend/scripts/test_no_match.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.chat as chat_router  # noqa: E402
from app import db  # noqa: E402
from app.schemas import ChatRequest, ParseResult  # noqa: E402
from app.seed_data import RESTAURANTS  # noqa: E402

DEMO_CONFIG = {
    "provider": "none",
    "api_key": "",
    "base_url": "",
    "model": "",
    "temperature": 0.3,
}


def main() -> int:
    db.init_db()
    db.upsert_restaurants(RESTAURANTS)

    # Keep the test offline/deterministic without touching the saved LLM config.
    original_get_config = db.get_llm_config
    db.get_llm_config = lambda: DEMO_CONFIG
    try:
        # 1) Strict default: "Cheap vegan breakfast" is infeasible -> explicit refusal.
        res = chat_router.chat(ChatRequest(message="Cheap vegan breakfast", limit=5))
        assert res.status == "no_match", res.status
        assert res.picks == [], [p["id"] for p in res.picks]
        assert "No suitable restaurant found" in res.summary, res.summary
        assert "did not relax" in res.summary, res.summary
        assert res.relaxed == [], res.relaxed
        assert res.structured.meal == "breakfast", res.structured
        assert res.structured.price_level == 1, res.structured
        assert "vegan" in res.structured.dietary, res.structured
        print("OK  strict refusal:", res.summary)

        # 2) Opt-in relaxation is applied AND disclosed in the summary.
        res2 = chat_router.chat(
            ChatRequest(message="Cheap vegan breakfast", limit=5, relax=True)
        )
        assert res2.status == "relaxed", res2.status
        assert res2.picks, "expected relaxed picks"
        assert "price_level" in res2.relaxed, res2.relaxed
        assert "relaxed the price filter" in res2.summary.lower(), res2.summary
        assert all(p["price_level"] != 1 for p in res2.picks), [
            p["price_level"] for p in res2.picks
        ]
        print("OK  disclosed relaxation:", res2.relaxed, [p["id"] for p in res2.picks])

        # 3) LLM-mode parse still refuses deterministically: the empty result is
        #    never handed to the LLM to explain (the old silent-relaxation path).
        original_parse = chat_router.parse_message
        chat_router.parse_message = lambda config, message: (
            ParseResult(meal="breakfast", price_level=1, dietary=["vegan"]),
            "llm",
        )
        try:
            res3 = chat_router.chat(ChatRequest(message="Cheap vegan breakfast", limit=5))
            assert res3.mode == "llm", res3.mode
            assert res3.status == "no_match", res3.status
            assert res3.picks == [], [p["id"] for p in res3.picks]
            assert "No suitable restaurant found" in res3.summary, res3.summary
            print("OK  LLM-mode refusal:", res3.summary)
        finally:
            chat_router.parse_message = original_parse

        # 4) A satisfiable request still returns picks with status "ok".
        res4 = chat_router.chat(ChatRequest(message="Vegan lunch near campus", limit=5))
        assert res4.status == "ok", res4.status
        assert res4.picks, "expected picks"
        assert res4.relaxed == [], res4.relaxed
        print("OK  normal request:", [p["id"] for p in res4.picks])

        # 5) LLM mode + opt-in relaxation: the disclosure is guaranteed even if
        #    the LLM summary omits it.
        original_explain = chat_router.explain_llm
        chat_router.parse_message = lambda config, message: (
            ParseResult(meal="breakfast", price_level=1, dietary=["vegan"]),
            "llm",
        )
        chat_router.explain_llm = lambda config, message, p, picks, relaxed=None: (
            "Here are some relaxed picks.",
            {},
        )
        try:
            res5 = chat_router.chat(
                ChatRequest(message="Cheap vegan breakfast", limit=5, relax=True)
            )
            assert res5.mode == "llm", res5.mode
            assert res5.status == "relaxed", res5.status
            assert res5.relaxed == ["price_level"], res5.relaxed
            assert res5.picks, "expected relaxed picks"
            assert "relaxed the price filter" in res5.summary.lower(), res5.summary
            print("OK  LLM relaxation disclosure enforced:", res5.summary)
        finally:
            chat_router.explain_llm = original_explain
            chat_router.parse_message = original_parse

        print("\nM1 no-match regression test passed ✔")
        return 0
    finally:
        db.get_llm_config = original_get_config


if __name__ == "__main__":
    sys.exit(main())
