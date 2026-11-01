"""Phase 1 regression: deterministic allergen enforcement.

Run: backend/.venv/bin/python backend/scripts/test_allergens.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.routers.chat as chat_router  # noqa: E402
import app.routers.restaurants as restaurants_router  # noqa: E402
from app import db  # noqa: E402
from app.allergens import detect_allergens, extract_allergens  # noqa: E402
from app.llm.parse import parse_demo, _validate  # noqa: E402
from app.recommend import filter_and_score, split_soft_matches  # noqa: E402
from app.schemas import ChatRequest  # noqa: E402
from app.seed_data import RESTAURANTS  # noqa: E402

DEMO_CONFIG = {
    "provider": "none",
    "api_key": "",
    "base_url": "",
    "model": "",
    "temperature": 0.3,
}

SEAFOOD_GROUPS = {"fish", "crustacean", "mollusk"}


def main() -> int:
    db.init_db()
    db.upsert_restaurants(RESTAURANTS)

    # Keep the test offline/deterministic without touching the saved LLM config.
    original_get_config = db.get_llm_config
    db.get_llm_config = lambda: DEMO_CONFIG
    try:
        # 1) Deterministic extraction from user messages.
        assert set(extract_allergens("lunch no seafood")) == SEAFOOD_GROUPS
        assert set(extract_allergens("I am allergic to shellfish")) == {
            "crustacean",
            "mollusk",
        }
        assert set(extract_allergens("no prawns or crab")) == {"crustacean"}
        assert set(extract_allergens("nut allergy")) == {"peanut", "tree-nut"}
        assert set(extract_allergens("no seafood or shellfish")) == SEAFOOD_GROUPS
        assert extract_allergens("no pork lunch") == []
        assert extract_allergens("I love seafood") == []
        # Dietary certifications vs allergen safety:
        # "-free" for nut/gluten is a dietary label; allergy phrasing is safety.
        assert extract_allergens("nut-free") == []
        assert extract_allergens("gluten-free") == []
        assert set(extract_allergens("allergic to nuts")) == {"peanut", "tree-nut"}
        assert set(extract_allergens("peanut allergy")) == {"peanut"}
        assert set(extract_allergens("celiac")) == {"gluten"}
        assert set(extract_allergens("lactose intolerant")) == {"dairy"}
        assert set(extract_allergens("dairy-free")) == {"dairy"}
        assert set(extract_allergens("peanut-free")) == {"peanut"}
        assert set(extract_allergens("shellfish-free")) == {"crustacean", "mollusk"}
        print("OK  allergen extraction (dietary vs allergen intent)")

        # Parsing separation: allergy -> allergens only; explicit diet -> dietary only.
        p_nut_free = parse_demo("nut-free lunch")
        assert p_nut_free.dietary == ["nut-free"], p_nut_free
        assert p_nut_free.allergens == [], p_nut_free
        p_gluten_free = parse_demo("gluten-free lunch")
        assert p_gluten_free.dietary == ["gluten-free"], p_gluten_free
        assert p_gluten_free.allergens == [], p_gluten_free
        p_allergy = parse_demo("cheap lunch I am allergic to nuts")
        assert p_allergy.dietary == [], p_allergy
        assert p_allergy.allergens == ["peanut", "tree-nut"], p_allergy
        p_celiac = parse_demo("celiac lunch")
        assert p_celiac.dietary == [], p_celiac
        assert p_celiac.allergens == ["gluten"], p_celiac
        print("OK  dietary labels and allergens are parsed separately")

        # LLM reconciliation: if a model returns both an allergen and the
        # redundant dietary label for an allergy, drop the dietary label.
        llm_data = {
            "meal": "lunch",
            "cuisines": [],
            "price_level": 1,
            "open_at": None,
            "dietary": ["nut-free"],
            "allergens": ["peanut", "tree-nut"],
            "keywords": [],
            "avoid": [],
            "notes": "",
        }
        p_llm = _validate(llm_data, "cheap lunch I am allergic to nuts")
        assert p_llm.dietary == [], p_llm
        assert p_llm.allergens == ["peanut", "tree-nut"], p_llm
        p_both = _validate(llm_data, "allergic to nuts, nut-free kitchen")
        assert p_both.dietary == ["nut-free"], p_both
        print("OK  LLM allergy output reconciled with dietary labels")

        # 2) Restaurant detection: explicit flags + text, with negation/exception checks.
        by_id = {r["id"]: r for r in RESTAURANTS}
        assert "fish" in detect_allergens(by_id["hana-sushi"])
        assert "crustacean" in detect_allergens(by_id["pokfulam-thai-grill"])
        assert "fish" in detect_allergens(by_id["water-street-noodle-house"])
        # "nut-free" must not become tree-nut; "water chestnut" is not a tree nut.
        assert "tree-nut" not in detect_allergens(by_id["green-bowl-salad-bar"])
        assert "tree-nut" not in detect_allergens(by_id["dim-sum-dynasty"])
        # "coconut cream" must not become dairy.
        assert "dairy" not in detect_allergens(by_id["sweet-corner-desserts"])
        print("OK  restaurant allergen detection (negation + exceptions)")

        # 3) Parsing + hard filtering: "lunch no seafood" excludes seafood venues.
        parsed = parse_demo("lunch no seafood")
        assert set(parsed.allergens) == SEAFOOD_GROUPS
        scored = filter_and_score(db.list_restaurants(), parsed)
        picks, soft_meta = split_soft_matches(scored, parsed)
        ids = {s["restaurant"]["id"] for s in picks}
        expected = {
            "cafe-88",
            "sun-kee-curry-house",
            "green-bowl-salad-bar",
        }
        assert ids == expected, ids
        assert soft_meta["soft_fallback"] is False, soft_meta
        for s in picks:
            assert not (detect_allergens(s["restaurant"]) & SEAFOOD_GROUPS), s[
                "restaurant"
            ]["id"]
        print("OK  'lunch no seafood' excludes seafood venues:", sorted(ids))

        # 3b) Allergy vs dietary label: nut allergy must not add dietary nut-free.
        #     Sweet Corner is excluded because it is a dessert venue, not a full
        #     lunch; Sun Kee is excluded by tree-nut. No full-meal lunch remains.
        nut_scored = filter_and_score(db.list_restaurants(), p_allergy)
        nut_picks, nut_meta = split_soft_matches(nut_scored, p_allergy)
        assert nut_picks == [], [s["restaurant"]["id"] for s in nut_picks]
        assert nut_meta["soft_fallback"] is False, nut_meta
        print("OK  'allergic to nuts' + lunch -> no full-meal safe option")

        # 3c) Explicit dietary label remains a soft preference, not an allergen filter.
        nutfree_scored = filter_and_score(db.list_restaurants(), p_nut_free)
        nutfree_picks, nutfree_meta = split_soft_matches(nutfree_scored, p_nut_free)
        assert {s["restaurant"]["id"] for s in nutfree_picks} == {
            "green-bowl-salad-bar"
        }, [s["restaurant"]["id"] for s in nutfree_picks]
        assert nutfree_meta["soft_fallback"] is False, nutfree_meta
        print("OK  'nut-free' -> Green Bowl (dietary label)")

        # 4) Chat response: safety disclosure + only safe picks.
        res = chat_router.chat(ChatRequest(message="lunch no seafood", limit=5))
        assert res.status == "ok", res.status
        assert "For safety, I excluded restaurants containing" in res.summary, res.summary
        assert res.structured.allergens == sorted(SEAFOOD_GROUPS), res.structured.allergens
        assert all(p["id"] in expected for p in res.picks), [p["id"] for p in res.picks]
        print("OK  chat safety disclosure:", res.summary)

        # 4b) Nut allergy + full lunch: no dessert/snack fallback; explicit refusal.
        res_nut = chat_router.chat(
            ChatRequest(message="cheap lunch I am allergic to nuts", limit=5)
        )
        assert res_nut.status == "no_match", res_nut.status
        assert res_nut.structured.dietary == [], res_nut.structured.dietary
        assert res_nut.structured.allergens == ["peanut", "tree-nut"], res_nut.structured.allergens
        assert res_nut.picks == [], [p["id"] for p in res_nut.picks]
        assert "No suitable restaurant found" in res_nut.summary, res_nut.summary
        print("OK  chat nut allergy + lunch -> refusal:", res_nut.summary)

        # 4c) Dietary nut-free is separate from allergen safety.
        res_nutfree = chat_router.chat(ChatRequest(message="nut-free lunch", limit=5))
        assert res_nutfree.structured.dietary == ["nut-free"], res_nutfree.structured.dietary
        assert res_nutfree.structured.allergens == [], res_nutfree.structured.allergens
        assert [p["id"] for p in res_nutfree.picks] == ["green-bowl-salad-bar"], [
            p["id"] for p in res_nutfree.picks
        ]
        assert (
            "For safety, I excluded restaurants containing"
            not in res_nutfree.summary
        ), res_nutfree.summary
        print("OK  chat dietary nut-free:", res_nutfree.summary)

        # 4d) Dietary gluten-free is separate from allergen safety.
        res_gf = chat_router.chat(ChatRequest(message="gluten-free lunch", limit=5))
        assert res_gf.structured.dietary == ["gluten-free"], res_gf.structured.dietary
        assert res_gf.structured.allergens == [], res_gf.structured.allergens
        assert (
            "For safety, I excluded restaurants containing" not in res_gf.summary
        ), res_gf.summary
        print("OK  chat dietary gluten-free is separate from allergen safety")

        # 4e) Celiac is a gluten allergy -> allergens only.
        res_celiac = chat_router.chat(ChatRequest(message="celiac lunch", limit=5))
        assert res_celiac.structured.dietary == [], res_celiac.structured.dietary
        assert res_celiac.structured.allergens == ["gluten"], res_celiac.structured.allergens
        assert (
            "For safety, I excluded restaurants containing gluten."
            in res_celiac.summary
        ), res_celiac.summary
        print("OK  chat celiac -> gluten allergen:", res_celiac.summary)

        # 5) Safety constraints are never relaxed.
        res2 = chat_router.chat(
            ChatRequest(message="Cheap vegan breakfast", limit=5, relax=True)
        )
        assert res2.status == "relaxed", res2.status
        assert "dietary" not in res2.relaxed, res2.relaxed
        assert "allergens" not in res2.relaxed, res2.relaxed
        res3 = chat_router.chat(
            ChatRequest(message="lunch no seafood", limit=5, relax=True)
        )
        assert res3.status == "ok", res3.status
        assert res3.relaxed == [], res3.relaxed
        assert all(p["id"] in expected for p in res3.picks), [p["id"] for p in res3.picks]
        print("OK  safety constraints not relaxed")

        # 6) API-level support for explore mode + meta.
        listed = restaurants_router.list_restaurants(
            meal="lunch",
            cuisine=None,
            price_level=None,
            dietary=None,
            allergens="seafood",
            open_at=None,
            q=None,
            limit=20,
        )
        listed_ids = {item["id"] for item in listed["items"]}
        assert listed_ids == expected, listed_ids
        meta = restaurants_router.meta()
        assert "allergen_options" in meta and "seafood" in meta["allergen_options"], meta
        assert "allergen_option_labels" in meta, meta
        print("OK  /api/restaurants + /api/meta allergen support")

        print("\nPhase 1 allergen regression test passed ✔")
        return 0
    finally:
        db.get_llm_config = original_get_config


if __name__ == "__main__":
    sys.exit(main())
