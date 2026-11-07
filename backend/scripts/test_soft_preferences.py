"""Regression: soft preferences (dietary, cuisine) use strict-first ranking with
a disclosed hard-only fallback.

Run: backend/.venv/bin/python backend/scripts/test_soft_preferences.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.chat as chat_router  # noqa: E402
import app.routers.restaurants as restaurants_router  # noqa: E402
from app import db  # noqa: E402
from app.llm.parse import _validate  # noqa: E402
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

    original_get_config = db.get_llm_config
    db.get_llm_config = lambda: DEMO_CONFIG
    try:
        # 0) LLM parse enrichment: explicit dish/cuisine/diet words must not be
        #    lost just because the model omitted them.
        llm_base = {
            "meal": "dinner",
            "cuisines": [],
            "price_level": 1,
            "open_at": None,
            "dietary": [],
            "allergens": [],
            "keywords": [],
            "avoid": [],
            "notes": "",
        }
        p = _validate(llm_base, "Cheap curry for dinner, student budget")
        assert p.cuisines == ["Indian"], p.cuisines
        p = _validate(llm_base, "cheap dessert")
        assert p.cuisines == ["Desserts"], p.cuisines
        p = _validate(llm_base, "cheap noodle lunch")
        assert p.cuisines == ["Noodles"], p.cuisines
        p = _validate(llm_base, "Vegan lunch near campus")
        assert {"vegetarian", "vegan"} <= set(p.dietary), p.dietary
        p = _validate(
            {
                **llm_base,
                "meal": "lunch",
                "price_level": None,
                "cuisines": ["Vegetarian"],
            },
            "Vegetarian lunch",
        )
        assert p.dietary == ["vegetarian"], p.dietary
        assert p.cuisines == [], p.cuisines
        print("OK  LLM parse enrichment (cuisine/dietary omitted by model)")

        # 1) Cuisine is strict when a match exists: only Sun Kee for "curry".
        res = chat_router.chat(
            ChatRequest(message="Cheap curry for dinner, student budget", limit=5)
        )
        assert res.status == "ok", res.status
        assert res.soft_fallback is False, res.soft_fallback
        assert [p["id"] for p in res.picks] == ["sun-kee-curry-house"], [
            p["id"] for p in res.picks
        ]
        print("OK  cuisine strict match:", [p["id"] for p in res.picks])

        # 2) Dietary is strict when a match exists: only vegan venues.
        res = chat_router.chat(ChatRequest(message="Vegan lunch near campus", limit=5))
        assert res.status == "ok", res.status
        assert res.soft_fallback is False, res.soft_fallback
        assert {p["id"] for p in res.picks} == {
            "cafe-88",
            "sun-kee-curry-house",
            "green-bowl-salad-bar",
            "jade-garden-vegetarian",
        }, [p["id"] for p in res.picks]
        print("OK  dietary strict match:", [p["id"] for p in res.picks])

        # 3) "Vegetarian" is a dietary preference, not a duplicate cuisine filter.
        res = chat_router.chat(ChatRequest(message="Vegetarian lunch", limit=10))
        assert res.soft_fallback is False, res.soft_fallback
        assert res.structured.cuisines == [], res.structured.cuisines
        assert {p["id"] for p in res.picks} == {
            "cafe-88",
            "sun-kee-curry-house",
            "dim-sum-dynasty",
            "green-bowl-salad-bar",
            "jade-garden-vegetarian",
        }, [p["id"] for p in res.picks]
        print("OK  vegetarian cuisine normalized into dietary")

        # 4) Food-type intent outranks price: cheap noodle -> pricier noodle venue.
        res = chat_router.chat(ChatRequest(message="Cheap noodle lunch", limit=5))
        assert res.status == "relaxed", res.status
        assert res.relaxed == ["price_level"], res.relaxed
        assert res.soft_fallback is False, res.soft_fallback
        assert res.unmet_soft == [], res.unmet_soft
        assert [p["id"] for p in res.picks] == ["water-street-noodle-house"], [
            p["id"] for p in res.picks
        ]
        assert not res.picks[0]["soft_mismatches"], res.picks[0]["soft_mismatches"]
        assert "relaxed the price filter" in res.summary.lower(), res.summary
        print("OK  food-type over price:", res.summary)

        # 4b) More food-type-over-price cases.
        cases = [
            ("Cheap sushi lunch", {"hana-sushi"}),
            ("Cheap Thai lunch", {"pokfulam-thai-grill"}),
            ("Cheap grilled lunch", {"pokfulam-thai-grill"}),
            (
                "Cheap healthy lunch",
                {"green-bowl-salad-bar", "jade-garden-vegetarian"},
            ),
            ("Cheap noodle breakfast", {"water-street-noodle-house"}),
        ]
        for message, expected in cases:
            res = chat_router.chat(ChatRequest(message=message, limit=5))
            assert res.status == "relaxed", (message, res.status)
            assert res.relaxed == ["price_level"], (message, res.relaxed)
            assert {p["id"] for p in res.picks} == expected, (
                message,
                [p["id"] for p in res.picks],
            )
        # No food-type intent -> hard refusal is preserved (M1 behavior).
        res = chat_router.chat(ChatRequest(message="Cheap vegan breakfast", limit=5))
        assert res.status == "no_match", res.status
        assert res.relaxed == [], res.relaxed
        print("OK  food-type over price cases + hard refusal preserved")

        # 5) Dietary fallback: no cheap vegan snack -> Sweet Corner + disclosure.
        res = chat_router.chat(ChatRequest(message="Cheap vegan snack", limit=5))
        assert res.status == "soft_fallback", res.status
        assert res.soft_fallback is True, res.soft_fallback
        assert res.unmet_soft == ["dietary"], res.unmet_soft
        assert [p["id"] for p in res.picks] == ["sweet-corner-desserts"], [
            p["id"] for p in res.picks
        ]
        assert res.picks[0]["soft_mismatches"] == ["dietary: vegan"], res.picks[0][
            "soft_mismatches"
        ]
        assert (
            "No restaurant matches all your preferences (dietary)" in res.summary
        ), res.summary
        print("OK  dietary fallback:", res.summary)

        # 6) The earlier "cheap dessert" case: strict cuisine match, no Sun Kee.
        res = chat_router.chat(ChatRequest(message="cheap dessert", limit=5))
        assert res.status == "ok", res.status
        assert res.soft_fallback is False, res.soft_fallback
        assert [p["id"] for p in res.picks] == ["sweet-corner-desserts"], [
            p["id"] for p in res.picks
        ]
        print("OK  cheap dessert -> Sweet Corner only")

        # 7) LLM mode: deterministic price-relaxation disclosure is enforced even
        #    if the LLM summary omits it.
        original_parse = chat_router.parse_message
        original_explain = chat_router.explain_llm
        chat_router.parse_message = lambda config, message: (
            ParseResult(meal="lunch", price_level=1, cuisines=["Noodles"]),
            "llm",
        )
        chat_router.explain_llm = (
            lambda config, message, p, picks, relaxed=None, soft_fallback=False, unmet_soft=None: (
                "Here are some cheap lunch options.",
                {},
            )
        )
        try:
            res = chat_router.chat(ChatRequest(message="Cheap noodle lunch", limit=5))
            assert res.mode == "llm", res.mode
            assert res.relaxed == ["price_level"], res.relaxed
            assert res.soft_fallback is False, res.soft_fallback
            assert [p["id"] for p in res.picks] == ["water-street-noodle-house"], [
                p["id"] for p in res.picks
            ]
            assert "relaxed the price filter" in res.summary.lower(), res.summary
            print("OK  LLM price-relaxation disclosure enforced:", res.summary)
        finally:
            chat_router.parse_message = original_parse
            chat_router.explain_llm = original_explain

        # 8) Explore endpoint: food-type intent outranks price.
        listed = restaurants_router.list_restaurants(
            meal="lunch",
            cuisine="Noodles",
            price_level=1,
            dietary=None,
            allergens=None,
            open_at=None,
            q=None,
            limit=20,
        )
        assert listed["status"] == "relaxed", listed
        assert listed["relaxed"] == ["price_level"], listed
        assert listed["soft_fallback"] is False, listed
        assert {i["id"] for i in listed["items"]} == {
            "water-street-noodle-house",
        }, [i["id"] for i in listed["items"]]
        assert not any(i["soft_mismatches"] for i in listed["items"]), listed["items"]
        print("OK  /api/restaurants food-type over price")

        # 8b) Explore endpoint still exposes hard-only fallback when no food-type
        # match exists at any price (e.g. Korean cuisine).
        listed = restaurants_router.list_restaurants(
            meal="lunch",
            cuisine="Korean",
            price_level=None,
            dietary=None,
            allergens=None,
            open_at=None,
            q=None,
            limit=20,
        )
        assert listed["status"] == "soft_fallback", listed
        assert listed["soft_fallback"] is True, listed
        assert listed["relaxed"] == [], listed
        assert listed["unmet_soft"] == ["cuisines"], listed
        assert all(i["soft_mismatches"] for i in listed["items"]), [
            i["soft_mismatches"] for i in listed["items"]
        ]
        print("OK  /api/restaurants fallback metadata")

        # 9) Explore endpoint strict match.
        listed = restaurants_router.list_restaurants(
            meal="dinner",
            cuisine="Indian",
            price_level=1,
            dietary=None,
            allergens=None,
            open_at=None,
            q=None,
            limit=20,
        )
        assert listed["soft_fallback"] is False, listed
        assert {i["id"] for i in listed["items"]} == {"sun-kee-curry-house"}, [
            i["id"] for i in listed["items"]
        ]
        print("OK  /api/restaurants strict cuisine match")

        # 10) Full meals exclude dessert/snack venues; snack requests still allow them.
        res = chat_router.chat(ChatRequest(message="Cheap lunch", limit=5))
        assert [p["id"] for p in res.picks] == ["sun-kee-curry-house"], [
            p["id"] for p in res.picks
        ]
        res = chat_router.chat(
            ChatRequest(message="Dinner at 22:30, anywhere", limit=5)
        )
        assert "sweet-corner-desserts" not in {p["id"] for p in res.picks}, [
            p["id"] for p in res.picks
        ]
        res = chat_router.chat(ChatRequest(message="Cheap dessert", limit=5))
        assert [p["id"] for p in res.picks] == ["sweet-corner-desserts"], [
            p["id"] for p in res.picks
        ]
        print("OK  full meals exclude dessert/snack venues")

        print("\nSoft-preference regression test passed ✔")
        return 0
    finally:
        db.get_llm_config = original_get_config


if __name__ == "__main__":
    sys.exit(main())
