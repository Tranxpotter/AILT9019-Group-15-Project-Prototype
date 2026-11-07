"""Phase 3 regression: constrained LLM re-ranking/selection.

Covers:
- validation of LLM output (unknown ids, duplicates, non-candidates, unsafe picks)
- re-ranking valid/mocked provider output and invalid-output fallback
- latency/timeout fallback
- chat pipeline integration (demo mode deterministic, LLM re-rank, fallback)
- preservation of M1 refusal, allergen safety, soft fallback and price relaxation

Run: backend/.venv/bin/python backend/scripts/test_rerank.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.llm.rerank as rerank_mod  # noqa: E402
import app.routers.chat as chat_router  # noqa: E402
from app import db  # noqa: E402
from app.llm.rerank import (  # noqa: E402
    SELECTION_DETERMINISTIC,
    SELECTION_FALLBACK,
    SELECTION_LLM,
    build_candidates,
    rerank,
    select_picks,
    validate_selection,
)
from app.recommend import search_ranked_pool  # noqa: E402
from app.schemas import ChatRequest, ParseResult  # noqa: E402
from app.seed_data import RESTAURANTS  # noqa: E402

DEMO_CONFIG = {
    "provider": "none",
    "api_key": "",
    "base_url": "",
    "model": "",
    "temperature": 0.3,
}
LLM_CONFIG = {
    "provider": "custom",
    "api_key": "",
    "base_url": "http://mock.invalid/v1",
    "model": "mock-model",
    "temperature": 0.3,
}


class FakeProvider:
    """Deterministic stand-in for a configured LLM provider."""

    def __init__(self, doc=None, error=None, sleep=0.0):
        self.doc = doc
        self.error = error
        self.sleep = sleep
        self.calls = 0

    def chat_json(self, system, user, schema, max_tokens=1024):
        self.calls += 1
        if self.sleep:
            time.sleep(self.sleep)
        if self.error:
            raise self.error
        return self.doc


def make_pool(p: ParseResult, limit: int = 15):
    pool, meta, effective, relaxed = search_ranked_pool(
        db.list_restaurants(), p, limit
    )
    candidates = build_candidates(pool)
    restaurants_by_id = {s["restaurant"]["id"]: s["restaurant"] for s in pool}
    return pool, meta, effective, relaxed, candidates, restaurants_by_id


def patch_provider(provider):
    original = rerank_mod.get_provider
    rerank_mod.get_provider = lambda config, timeout=None: provider
    return original


def main() -> int:
    db.init_db()
    db.upsert_restaurants(RESTAURANTS)

    lunch = ParseResult(meal="lunch")
    pool, _meta, _eff, _relaxed, candidates, rby = make_pool(lunch)
    ids = [c["id"] for c in candidates]
    assert len(ids) >= 6, ids
    print("OK  candidate generation:", len(ids), "lunch candidates")

    # ------------------------------------------------------------------ #
    # 1) Validation unit tests (no provider involved)
    # ------------------------------------------------------------------ #
    data = {
        "picks": [
            {"id": ids[2], "reason": "best fit for soup noodles"},
            {"id": ids[0], "reason": "closest walk"},
        ],
        "summary": "Picked for soup + distance.",
    }
    v = validate_selection(data, candidates, lunch, 5, rby)
    assert v.ok and v.ordered_ids == [ids[2], ids[0]], v
    assert v.reasons[ids[2]] == "best fit for soup noodles", v.reasons
    assert v.summary == "Picked for soup + distance.", v.summary
    assert not v.rejected, v.rejected
    print("OK  validation: valid reorder + reasons preserved")

    v = validate_selection(
        {"picks": [{"id": "invented-bistro", "reason": "hallucination"}]},
        candidates,
        lunch,
        5,
        rby,
    )
    assert v.ordered_ids == [] and not v.ok, v
    assert v.rejected and v.rejected[0]["reason"] == "unknown_id", v.rejected
    print("OK  validation: unknown / non-candidate id rejected")

    v = validate_selection(
        {
            "picks": [
                {"id": ids[0], "reason": "first"},
                {"id": ids[0], "reason": "again"},
            ]
        },
        candidates,
        lunch,
        5,
        rby,
    )
    assert v.ordered_ids == [ids[0]], v
    assert any(r["reason"] == "duplicate" for r in v.rejected), v.rejected
    print("OK  validation: duplicate id rejected")

    v = validate_selection(
        {"picks": [{"id": ids[1], "reason": "x"}] * 8}, candidates, lunch, 3, rby
    )
    assert len(v.ordered_ids) <= 3, v
    print("OK  validation: selection truncated to limit")

    v = validate_selection({"picks": []}, candidates, lunch, 5, rby)
    assert v.ordered_ids == [] and not v.ok, v
    v = validate_selection({"picks": {"id": ids[0]}}, candidates, lunch, 5, rby)
    assert v.ordered_ids == [] and not v.ok, v
    v = validate_selection(None, candidates, lunch, 5, rby)
    assert v.ordered_ids == [] and not v.ok, v
    print("OK  validation: empty / malformed output rejected")

    # Unsafe picks: re-validation catches constraints the pool did not apply
    # (simulates an LLM trying to override safety).
    assert "hana-sushi" in ids, ids
    v = validate_selection(
        {"picks": [{"id": "hana-sushi", "reason": "great sashimi"}]},
        candidates,
        ParseResult(meal="lunch", allergens=["fish"]),
        5,
        rby,
    )
    assert v.ordered_ids == [], v
    assert v.rejected[0]["reason"] == "unsafe:allergens", v.rejected
    print("OK  validation: allergen violation rejected (safety)")

    v = validate_selection(
        {"picks": [{"id": "water-street-noodle-house", "reason": "cheap"}]},
        candidates,
        ParseResult(meal="lunch", price_level=1),
        5,
        rby,
    )
    assert v.ordered_ids == [], v
    assert v.rejected[0]["reason"] == "unsafe:price_level", v.rejected
    print("OK  validation: price-band violation rejected")

    v = validate_selection(
        {"picks": [{"id": ids[0], "reason": "x"}]},
        candidates,
        ParseResult(meal="lunch", open_at="03:00"),
        5,
        rby,
    )
    assert v.ordered_ids == [], v
    assert v.rejected[0]["reason"] == "unsafe:open_at", v.rejected
    print("OK  validation: opening-time violation rejected")

    v = validate_selection(
        {"picks": [{"id": "cafe-88", "reason": "x"}]},
        candidates,
        ParseResult(meal="dinner"),
        5,
        rby,
    )
    assert v.ordered_ids == [], v
    assert v.rejected[0]["reason"] == "unsafe:meal", v.rejected
    print("OK  validation: meal violation rejected")

    # The re-ranker must respect the food-type price-relaxation state.
    relaxed_parse = ParseResult(meal="lunch", price_level=1, cuisines=["Noodles"])
    rpool, _m, reff, rrelaxed = search_ranked_pool(
        db.list_restaurants(), relaxed_parse, 15
    )
    assert rrelaxed == ["price_level"] and reff.price_level is None, rrelaxed
    rcands = build_candidates(rpool)
    rrby = {s["restaurant"]["id"]: s["restaurant"] for s in rpool}
    strict_v = validate_selection(
        {"picks": [{"id": "water-street-noodle-house", "reason": "noodles"}]},
        rcands,
        relaxed_parse,
        5,
        rrby,
    )
    assert strict_v.rejected[0]["reason"] == "unsafe:price_level", strict_v.rejected
    relaxed_v = validate_selection(
        {"picks": [{"id": "water-street-noodle-house", "reason": "noodles"}]},
        rcands,
        reff,
        5,
        rrby,
    )
    assert relaxed_v.ordered_ids == ["water-street-noodle-house"], relaxed_v
    print("OK  validation: respects relaxed price state")

    # ------------------------------------------------------------------ #
    # 2) select_picks with mocked providers
    # ------------------------------------------------------------------ #
    fake = FakeProvider(
        doc={
            "picks": [
                {"id": ids[4], "reason": "LLM first"},
                {"id": ids[1], "reason": "LLM second"},
            ],
            "summary": "LLM order.",
        }
    )
    original = patch_provider(fake)
    try:
        out = select_picks(pool, lunch, 5, LLM_CONFIG, "lunch please")
    finally:
        rerank_mod.get_provider = original
    expected = [ids[4], ids[1]] + [
        i for i in ids if i not in {ids[4], ids[1]}
    ][:3]
    assert out.selection_mode == SELECTION_LLM, out.selection_mode
    assert [s["restaurant"]["id"] for s in out.picks] == expected, [
        s["restaurant"]["id"] for s in out.picks
    ]
    assert out.reasons[ids[4]] == "LLM first", out.reasons
    assert out.candidate_count == len(ids), out.candidate_count
    assert fake.calls == 1, fake.calls
    print("OK  select_picks: valid LLM order applied + missing slots repaired")

    fake = FakeProvider(doc={"picks": [{"id": "fake-place"}], "summary": "x"})
    original = patch_provider(fake)
    try:
        out = select_picks(pool, lunch, 5, LLM_CONFIG, "lunch please")
    finally:
        rerank_mod.get_provider = original
    assert out.selection_mode == SELECTION_FALLBACK, out.selection_mode
    assert [s["restaurant"]["id"] for s in out.picks] == ids[:5], [
        s["restaurant"]["id"] for s in out.picks
    ]
    print("OK  select_picks: invalid ids -> deterministic fallback")

    fake = FakeProvider(doc={"picks": [], "summary": "nothing"})
    original = patch_provider(fake)
    try:
        out = select_picks(pool, lunch, 5, LLM_CONFIG, "lunch please")
    finally:
        rerank_mod.get_provider = original
    assert out.selection_mode == SELECTION_FALLBACK, out.selection_mode
    assert [s["restaurant"]["id"] for s in out.picks] == ids[:5], out.picks
    print("OK  select_picks: empty selection -> deterministic fallback")

    fake = FakeProvider(error=RuntimeError("provider down"))
    original = patch_provider(fake)
    try:
        out = select_picks(pool, lunch, 5, LLM_CONFIG, "lunch please")
    finally:
        rerank_mod.get_provider = original
    assert out.selection_mode == SELECTION_FALLBACK, out.selection_mode
    assert "provider down" in out.error, out.error
    print("OK  select_picks: provider error -> deterministic fallback")

    fake = FakeProvider(doc={"picks": [{"id": ids[0], "reason": "x"}]})
    original = patch_provider(fake)
    try:
        out = select_picks(pool, lunch, 5, LLM_CONFIG, "lunch please", enabled=False)
    finally:
        rerank_mod.get_provider = original
    assert out.selection_mode == SELECTION_DETERMINISTIC, out.selection_mode
    assert fake.calls == 0, fake.calls
    print("OK  select_picks: feature flag disables the LLM call")

    # Direct rerank timeout (bounded wall-clock budget).
    slow = FakeProvider(
        doc={"picks": [{"id": ids[0], "reason": "slow"}], "summary": "s"},
        sleep=0.5,
    )
    original = patch_provider(slow)
    try:
        started = time.monotonic()
        call = rerank(
            LLM_CONFIG,
            "lunch",
            lunch,
            candidates,
            5,
            timeout=0.05,
        )
        elapsed = time.monotonic() - started
    finally:
        rerank_mod.get_provider = original
    assert not call.ok, call
    assert "timed out" in call.error, call.error
    assert elapsed < 0.45, elapsed
    print(f"OK  rerank: timeout after {elapsed:.2f}s -> fallback signal")

    # ------------------------------------------------------------------ #
    # 3) Chat pipeline integration
    # ------------------------------------------------------------------ #
    original_get_config = db.get_llm_config
    original_parse = chat_router.parse_message
    original_explain = chat_router.explain_llm
    try:
        # Demo mode is always deterministic.
        db.get_llm_config = lambda: DEMO_CONFIG
        res = chat_router.chat(
            ChatRequest(message="Vegan lunch near campus", limit=5)
        )
        assert res.selection_mode == SELECTION_DETERMINISTIC, res.selection_mode
        assert res.candidate_count == 4, res.candidate_count
        assert {p["id"] for p in res.picks} == {
            "cafe-88",
            "sun-kee-curry-house",
            "green-bowl-salad-bar",
            "jade-garden-vegetarian",
        }, [p["id"] for p in res.picks]
        print("OK  demo mode: deterministic selection, session metadata exposed")

        # LLM mode: valid re-rank drives order + reasons.
        db.get_llm_config = lambda: LLM_CONFIG
        chat_router.parse_message = lambda config, message: (ParseResult(meal="lunch"), "llm")
        chat_router.explain_llm = lambda config, message, p, picks, relaxed=None, soft_fallback=False, unmet_soft=None: (
            "Here is a lunch selection.",
            {},
        )
        fake = FakeProvider(
            doc={
                "picks": [
                    {"id": ids[5], "reason": "LLM top pick"},
                    {"id": ids[2], "reason": "LLM second pick"},
                    {"id": ids[0], "reason": "LLM third pick"},
                ],
                "summary": "Ordered for you.",
            }
        )
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(ChatRequest(message="lunch", limit=3))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.mode == "llm", res.mode
        assert res.selection_mode == SELECTION_LLM, res.selection_mode
        assert res.candidate_count == len(ids), res.candidate_count
        assert [p["id"] for p in res.picks] == [ids[5], ids[2], ids[0]], [
            p["id"] for p in res.picks
        ]
        assert [p["reason"] for p in res.picks] == [
            "LLM top pick",
            "LLM second pick",
            "LLM third pick",
        ], [p["reason"] for p in res.picks]
        print("OK  chat: LLM re-rank order + reasons applied")

        # Parse falling back to the keyword parser must NOT disable the selector:
        # the provider is still configured, so selection still runs.
        chat_router.parse_message = lambda config, message: (ParseResult(meal="lunch"), "demo")
        fake = FakeProvider(
            doc={
                "picks": [{"id": ids[4], "reason": "keyword-parse rerank"}],
                "summary": "x",
            }
        )
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(ChatRequest(message="lunch", limit=2))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.mode == "demo", res.mode
        assert res.selection_mode == SELECTION_LLM, res.selection_mode
        assert res.picks[0]["id"] == ids[4], [p["id"] for p in res.picks]
        assert res.picks[0]["reason"] == "keyword-parse rerank", res.picks[0]
        assert not res.selection_note, res.selection_note
        print("OK  chat: demo parse fallback still runs LLM selection")

        # LLM mode: invalid output falls back deterministically.
        fake = FakeProvider(doc={"picks": [{"id": "not-a-real-place", "reason": "x"}]})
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(ChatRequest(message="lunch", limit=3))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.selection_mode == SELECTION_FALLBACK, res.selection_mode
        assert res.selection_note, res.selection_note
        assert [p["id"] for p in res.picks] == ids[:3], [p["id"] for p in res.picks]
        print("OK  chat: invalid LLM output -> deterministic fallback (+note)")

        # Allergen safety: the selector cannot reintroduce a filtered venue.
        allergen_parse = ParseResult(
            meal="lunch", allergens=["fish", "crustacean", "mollusk"]
        )
        db.get_llm_config = lambda: DEMO_CONFIG
        chat_router.parse_message = lambda config, message: (allergen_parse, "demo")
        res = chat_router.chat(ChatRequest(message="Lunch, no seafood", limit=5))
        assert res.structured.allergens == ["crustacean", "fish", "mollusk"], res.structured.allergens
        assert "hana-sushi" not in {p["id"] for p in res.picks}, [
            p["id"] for p in res.picks
        ]
        assert res.selection_mode == SELECTION_DETERMINISTIC, res.selection_mode

        # LLM re-rank that tries an unsafe venue: rejected -> all-safe fallback.
        db.get_llm_config = lambda: LLM_CONFIG
        chat_router.parse_message = lambda config, message: (allergen_parse, "llm")
        fake = FakeProvider(
            doc={
                "picks": [
                    {"id": "hana-sushi", "reason": "sashimi is great"},
                    {"id": "water-street-noodle-house", "reason": "noodles"},
                ],
                "summary": "x",
            }
        )
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(ChatRequest(message="Lunch, no seafood", limit=5))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        picked = {p["id"] for p in res.picks}
        assert "hana-sushi" not in picked, picked
        assert "water-street-noodle-house" not in picked, picked
        assert res.selection_mode == SELECTION_FALLBACK, res.selection_mode
        assert "For safety, I excluded restaurants" in res.summary, res.summary
        print("OK  chat: unsafe LLM picks rejected, allergen safety preserved")

        # M1 refusal preserved: the selector is never consulted on no-match.
        db.get_llm_config = lambda: LLM_CONFIG
        chat_router.parse_message = lambda config, message: (
            ParseResult(meal="breakfast", price_level=1, dietary=["vegetarian", "vegan"]),
            "llm",
        )
        exploding = FakeProvider(error=AssertionError("rerank must not run on no_match"))
        original_rerank_provider = patch_provider(exploding)
        try:
            res = chat_router.chat(ChatRequest(message="Cheap vegan breakfast", limit=5))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.status == "no_match", res.status
        assert res.picks == [], res.picks
        assert res.selection_mode == SELECTION_DETERMINISTIC, res.selection_mode
        assert res.candidate_count == 0, res.candidate_count
        assert exploding.calls == 0, exploding.calls
        assert "No suitable restaurant found." in res.summary, res.summary
        print("OK  chat: M1 refusal preserved (re-ranker not called)")

        # Soft fallback preserved (demo + LLM re-rank paths).
        db.get_llm_config = lambda: DEMO_CONFIG
        chat_router.parse_message = original_parse
        res = chat_router.chat(ChatRequest(message="Cheap vegan snack", limit=5))
        assert res.status == "soft_fallback", res.status
        assert res.soft_fallback is True
        assert [p["id"] for p in res.picks] == ["sweet-corner-desserts"], [
            p["id"] for p in res.picks
        ]
        assert res.selection_mode == SELECTION_DETERMINISTIC, res.selection_mode

        db.get_llm_config = lambda: LLM_CONFIG
        chat_router.parse_message = lambda config, message: (ParseResult(meal="snack", price_level=1, dietary=["vegan"]), "llm")
        chat_router.explain_llm = lambda config, message, p, picks, relaxed=None, soft_fallback=False, unmet_soft=None: (
            "Closest snack options.",
            {},
        )
        fake = FakeProvider(
            doc={
                "picks": [{"id": "sweet-corner-desserts", "reason": "closest fit"}],
                "summary": "x",
            }
        )
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(ChatRequest(message="Cheap vegan snack", limit=5))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.status == "soft_fallback", res.status
        assert res.soft_fallback is True
        assert res.selection_mode == SELECTION_LLM, res.selection_mode
        assert "No restaurant matches all your preferences" in res.summary, res.summary
        print("OK  chat: soft fallback preserved with LLM re-rank")

        # Price relaxation disclosure still enforced with LLM re-rank.
        db.get_llm_config = lambda: LLM_CONFIG
        chat_router.parse_message = lambda config, message: (
            ParseResult(meal="lunch", price_level=1, cuisines=["Noodles"]),
            "llm",
        )
        fake = FakeProvider(
            doc={
                "picks": [{"id": "water-street-noodle-house", "reason": "noodle soup"}],
                "summary": "Noodle pick.",
            }
        )
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(ChatRequest(message="Cheap noodle lunch", limit=5))
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.status == "relaxed", res.status
        assert res.relaxed == ["price_level"], res.relaxed
        assert res.selection_mode == SELECTION_LLM, res.selection_mode
        assert [p["id"] for p in res.picks] == ["water-street-noodle-house"], [
            p["id"] for p in res.picks
        ]
        assert "relaxed the price filter" in res.summary.lower(), res.summary
        print("OK  chat: price relaxation state respected + disclosed")

        # Request-level feature flag disables re-ranking.
        chat_router.parse_message = lambda config, message: (ParseResult(meal="lunch"), "llm")
        fake = FakeProvider(doc={"picks": [{"id": ids[0], "reason": "x"}]})
        original_rerank_provider = patch_provider(fake)
        try:
            res = chat_router.chat(
                ChatRequest(message="lunch", limit=3, rerank=False)
            )
        finally:
            rerank_mod.get_provider = original_rerank_provider
        assert res.selection_mode == SELECTION_DETERMINISTIC, res.selection_mode
        assert fake.calls == 0, fake.calls
        assert [p["id"] for p in res.picks] == ids[:3], [p["id"] for p in res.picks]
        print("OK  chat: rerank=False request override -> deterministic")

        # Latency: a slow selector never stalls the response past its budget.
        db.get_llm_config = lambda: LLM_CONFIG
        chat_router.parse_message = lambda config, message: (ParseResult(meal="lunch"), "llm")
        slow = FakeProvider(
            doc={"picks": [{"id": ids[0], "reason": "x"}]}, sleep=0.5
        )
        original_rerank_provider = patch_provider(slow)
        original_timeout = rerank_mod.LLM_RERANK_TIMEOUT_SECONDS
        rerank_mod.LLM_RERANK_TIMEOUT_SECONDS = 0.05
        try:
            started = time.monotonic()
            res = chat_router.chat(ChatRequest(message="lunch", limit=3))
            elapsed = time.monotonic() - started
        finally:
            rerank_mod.get_provider = original_rerank_provider
            rerank_mod.LLM_RERANK_TIMEOUT_SECONDS = original_timeout
        assert res.selection_mode == SELECTION_FALLBACK, res.selection_mode
        assert "timed out" in res.selection_note, res.selection_note
        assert elapsed < 0.45, elapsed
        assert [p["id"] for p in res.picks] == ids[:3], [p["id"] for p in res.picks]
        print(f"OK  chat: re-rank timeout after {elapsed:.2f}s -> fallback")
    finally:
        db.get_llm_config = original_get_config
        chat_router.parse_message = original_parse
        chat_router.explain_llm = original_explain

    print("\nConstrained re-ranking regression test passed ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
