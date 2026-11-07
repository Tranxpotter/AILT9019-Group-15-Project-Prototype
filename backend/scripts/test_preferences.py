"""Phase 2 regression: richer preferences + hybrid retrieval/weighted ranking.

Run: backend/.venv/bin/python backend/scripts/test_preferences.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.chat as chat_router  # noqa: E402
import app.routers.restaurants as restaurants_router  # noqa: E402
from app import db  # noqa: E402
from app.llm.parse import _validate  # noqa: E402
from app.schemas import ChatRequest  # noqa: E402
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

    original_get_config = db.get_llm_config
    db.get_llm_config = lambda: DEMO_CONFIG
    try:
        # 1) Soup/wet preference: Water Street is the only strict match.
        res = chat_router.chat(
            ChatRequest(
                message="Lunch, prefer wet/soup food like soup noodles", limit=5
            )
        )
        assert res.status == "ok", res.status
        assert res.soft_fallback is False, res.soft_fallback
        assert res.structured.dish_intent == ["soup noodles"], res.structured.dish_intent
        assert set(res.structured.texture) == {"soup", "wet"}, res.structured.texture
        assert [p["id"] for p in res.picks] == ["water-street-noodle-house"], [
            p["id"] for p in res.picks
        ]
        assert any(
            "matches dish: soup noodles" in m for m in res.picks[0]["matched"]
        ), res.picks[0]["matched"]
        print("OK  soup noodles -> Water Street:", res.summary)

        # 2) Texture preference: spicy lunch venues.
        res = chat_router.chat(
            ChatRequest(message="Lunch, prefer something spicy", limit=5)
        )
        assert res.soft_fallback is False, res.soft_fallback
        assert {p["id"] for p in res.picks} == {
            "sun-kee-curry-house",
            "pokfulam-thai-grill",
        }, [p["id"] for p in res.picks]
        print("OK  spicy preference:", [p["id"] for p in res.picks])

        # 3) Cuisine + vibe preference.
        res = chat_router.chat(
            ChatRequest(message="Lunch, prefer healthy and light", limit=5)
        )
        assert res.soft_fallback is False, res.soft_fallback
        assert {p["id"] for p in res.picks} == {
            "green-bowl-salad-bar",
            "jade-garden-vegetarian",
        }, [p["id"] for p in res.picks]
        print("OK  healthy + light preference:", [p["id"] for p in res.picks])

        # 4) Grilled texture.
        res = chat_router.chat(ChatRequest(message="Lunch, prefer grilled", limit=5))
        assert [p["id"] for p in res.picks] == ["pokfulam-thai-grill"], [
            p["id"] for p in res.picks
        ]
        print("OK  grilled preference")

        # 5) Raw fish -> sashimi dish intent.
        res = chat_router.chat(ChatRequest(message="Lunch, prefer raw fish", limit=5))
        assert [p["id"] for p in res.picks] == ["hana-sushi"], [
            p["id"] for p in res.picks
        ]
        print("OK  raw fish -> Hana Sushi")

        # 6) Preference fallback: no grilled snack -> Sweet Corner + disclosure.
        res = chat_router.chat(ChatRequest(message="Snack, prefer grilled", limit=5))
        assert res.status == "soft_fallback", res.status
        assert res.soft_fallback is True, res.soft_fallback
        assert res.unmet_soft == ["preferences"], res.unmet_soft
        assert [p["id"] for p in res.picks] == ["sweet-corner-desserts"], [
            p["id"] for p in res.picks
        ]
        assert res.picks[0]["soft_mismatches"] == ["texture: grilled"], res.picks[0][
            "soft_mismatches"
        ]
        assert (
            "No restaurant matches all your preferences (preference)" in res.summary
        ), res.summary
        print("OK  preference fallback:", res.summary)

        # 7) Late-night dinner: dessert venue excluded for full meals; fallback.
        res = chat_router.chat(
            ChatRequest(message="Dinner, prefer late night", limit=5)
        )
        assert res.status == "soft_fallback", res.status
        assert res.unmet_soft == ["preferences"], res.unmet_soft
        assert "sweet-corner-desserts" not in {p["id"] for p in res.picks}, [
            p["id"] for p in res.picks
        ]
        assert (
            "No restaurant matches all your preferences (preference)" in res.summary
        ), res.summary
        print("OK  late-night dinner fallback")

        # 8) LLM omission: deterministic preference enrichment.
        llm_data = {
            "meal": "lunch",
            "cuisines": [],
            "dish_intent": [],
            "texture": [],
            "vibe": [],
            "price_level": None,
            "open_at": None,
            "dietary": [],
            "allergens": [],
            "keywords": [],
            "avoid": [],
            "notes": "",
        }
        p = _validate(
            llm_data, "Lunch, prefer wet/soup food like soup noodles"
        )
        assert p.dish_intent == ["soup noodles"], p.dish_intent
        assert set(p.texture) == {"soup", "wet"}, p.texture
        print("OK  LLM preference enrichment")

        # 9) Hybrid ranking within a broader strict set: soup lunch, Water Street top.
        res = chat_router.chat(ChatRequest(message="Lunch, prefer soup", limit=5))
        assert res.soft_fallback is False, res.soft_fallback
        assert res.picks[0]["id"] == "water-street-noodle-house", [
            p["id"] for p in res.picks
        ]
        print("OK  BM25/hybrid ranking top pick:", res.picks[0]["id"])

        # 10) Explore endpoint supports preference query params.
        listed = restaurants_router.list_restaurants(
            meal="lunch",
            cuisine=None,
            price_level=None,
            dietary=None,
            allergens=None,
            dish_intent="soup noodles",
            texture="soup",
            vibe=None,
            open_at=None,
            q=None,
            limit=20,
        )
        assert listed["soft_fallback"] is False, listed
        assert {i["id"] for i in listed["items"]} == {
            "water-street-noodle-house"
        }, [i["id"] for i in listed["items"]]
        print("OK  /api/restaurants preference query")

        # 11) Meta exposes preference options.
        meta = restaurants_router.meta()
        assert "preference_options" in meta, meta
        assert "soup noodles" in meta["preference_options"]["dish_intent"], meta
        print("OK  /api/meta preference options")

        print("\nPhase 2 preference regression test passed ✔")
        return 0
    finally:
        db.get_llm_config = original_get_config


if __name__ == "__main__":
    sys.exit(main())
