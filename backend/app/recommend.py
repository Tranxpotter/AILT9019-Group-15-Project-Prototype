"""Deterministic filtering + scoring over the restaurant dataset.

The LLM (or keyword parser) only produces structured filters; the ranking logic
lives here so recommendations are reproducible and testable.
"""
from __future__ import annotations

from typing import Iterable

from .allergens import detect_allergens
from .preferences import match_preferences, normalize_preference_tags
from .retrieval import bm25, build_index, build_query_terms
from .schemas import ParseResult

PRICE_SYMBOL = {1: "$", 2: "$$", 3: "$$$"}

# "Full meals" should not return dessert/snack venues even if those venues are
# open at that time or list the meal in meal_categories.
FULL_MEALS = {"breakfast", "lunch", "dinner"}
_SNACK_MARKERS = (
    "dessert",
    "desserts",
    "snack",
    "sweets",
    "sweet",
    "bakery",
    "ice cream",
    "cake",
)


def _is_snack_venue(restaurant: dict) -> bool:
    """True for dessert/snack venues that should not appear for full meals."""
    text = " ".join(
        [str(restaurant.get("cuisine", ""))]
        + [str(t) for t in (restaurant.get("cuisine_tags") or [])]
        + [str(t) for t in (restaurant.get("tags") or [])]
    ).lower()
    return any(marker in text for marker in _SNACK_MARKERS)


def _open_at(restaurant: dict, time_min: int) -> bool:
    for slot in restaurant.get("opening") or []:
        try:
            open_min = int(slot["open"][:2]) * 60 + int(slot["open"][3:5])
            close_min = int(slot["close"][:2]) * 60 + int(slot["close"][3:5])
        except (KeyError, TypeError, ValueError):
            continue
        if close_min >= open_min:
            # normal window
            if open_min <= time_min <= close_min:
                return True
        else:
            # window crosses midnight, e.g. 12:00-01:00
            if time_min >= open_min or time_min <= close_min:
                return True
    return False


def _text_haystack(restaurant: dict) -> str:
    parts = [
        restaurant.get("name", ""),
        restaurant.get("cuisine", ""),
        " ".join(restaurant.get("cuisine_tags") or []),
        " ".join(restaurant.get("tags") or []),
        restaurant.get("description", ""),
        restaurant.get("area", ""),
    ]
    parts += [i.get("name", "") for i in (restaurant.get("menu") or [])]
    parts += [i.get("description", "") for i in (restaurant.get("menu") or [])]
    return " ".join(parts).lower()


def _cuisine_match(restaurant: dict, cuisines: list[str]) -> bool:
    """True when the venue matches at least one requested cuisine."""
    wanted = [c.strip().lower() for c in cuisines if c and c.strip()]
    if not wanted:
        return True
    actual = {
        str(restaurant.get("cuisine", "")).lower(),
        str(restaurant.get("name", "")).lower(),
    }
    actual |= {str(t).lower() for t in (restaurant.get("cuisine_tags") or [])}
    actual |= {str(t).lower() for t in (restaurant.get("tags") or [])}
    return any(w in a for w in wanted for a in actual)


def _time_minutes(open_at: str | None) -> int | None:
    """Parse 'HH:MM' into minutes, or None when absent/unparseable."""
    if not open_at:
        return None
    try:
        return int(str(open_at)[:2]) * 60 + int(str(open_at)[3:5])
    except (ValueError, TypeError):
        return None


def hard_constraint_violation(restaurant: dict, p: ParseResult) -> str | None:
    """Return the first hard constraint the venue violates, or None when safe.

    This is the authoritative safety check. It is used both when building the
    candidate pool and when validating any LLM-selected pick, so the LLM can
    never reintroduce a venue that violates allergens, meal, price/relaxation
    state, opening time, or `avoid`.
    """
    meal = (p.meal or "").strip().lower() or None
    if meal and meal not in (restaurant.get("meal_categories") or []):
        return "meal"
    # Full meals should not return dessert/snack venues.
    if meal in FULL_MEALS and _is_snack_venue(restaurant):
        return "meal"
    price = p.price_level
    if price and restaurant.get("price_level") != price:
        return "price_level"
    time_min = _time_minutes(p.open_at)
    if time_min is not None and not _open_at(restaurant, time_min):
        return "open_at"
    # Safety-critical: never accept a venue that may contain a requested allergen.
    wanted_allergens = set(p.allergens or [])
    if wanted_allergens and wanted_allergens & detect_allergens(restaurant):
        return "allergens"
    hay = _text_haystack(restaurant)
    if any(a.lower() in hay for a in (p.avoid or []) if a):
        return "avoid"
    return None


def filter_and_score(restaurants: Iterable[dict], p: ParseResult) -> list[dict]:
    """Return all hard-constraint matches, scored and annotated with soft flags.

    Hard constraints: meal, price, open_at, allergens, avoid.
    Soft preferences: dietary, cuisines, dish_intent/texture/vibe.
    Hybrid ranking adds BM25 lexical relevance over restaurant documents.
    """
    restaurants = list(restaurants)
    index = build_index(restaurants)
    query_terms = build_query_terms(p)

    meal = (p.meal or "").strip().lower() or None
    price = p.price_level
    wanted_dietary = [d for d in (p.dietary or []) if d]
    wanted_cuisines = [c for c in (p.cuisines or []) if c]

    scored = []
    for idx, r in enumerate(restaurants):
        # Hard constraints (shared with LLM re-rank validation).
        if hard_constraint_violation(r, p):
            continue

        hay = _text_haystack(r)

        # Soft preferences
        dietary = r.get("dietary") or []
        dietary_ok = all(d in dietary for d in wanted_dietary)
        cuisine_ok = _cuisine_match(r, wanted_cuisines)
        pref = match_preferences(r, p)
        preference_ok = pref["ok"]
        soft_ok = dietary_ok and cuisine_ok and preference_ok

        score = round(r.get("rating", 0) * 10, 1)
        reasons = []
        if meal:
            score += 8
            reasons.append(f"serves {meal}")
        hit_cuisine = [c for c in wanted_cuisines if _cuisine_match(r, [c])]
        if wanted_cuisines and hit_cuisine:
            score += 6
            reasons.append(",".join(hit_cuisine[:2]).title())
        if price:
            reasons.append(f"~{PRICE_SYMBOL.get(price, '')}")
        if wanted_dietary and dietary_ok:
            score += 4
            reasons.append("matches dietary: " + "+".join(wanted_dietary))
        if p.dish_intent and pref["dish_intent_ok"]:
            score += 6
            reasons.append("matches dish: " + "/".join(p.dish_intent))
        if p.texture and pref["texture_ok"]:
            score += 4
            reasons.append("matches texture: " + "/".join(p.texture))
        if p.vibe and pref["vibe_ok"]:
            score += 3
            reasons.append("matches vibe: " + "/".join(p.vibe))
        kw_hits = [k for k in (p.keywords or []) if len(k) >= 3 and k.lower() in hay]
        for k in kw_hits[:3]:
            score += 2
        if kw_hits:
            reasons.append("matches your keywords")
        if r.get("walk_minutes", 99) <= 5:
            score += 3
            reasons.append("very close walk")
        elif r.get("walk_minutes", 99) <= 10:
            score += 1
        if not reasons:
            reasons = [r.get("cuisine", "")]

        soft_mismatches = []
        if wanted_dietary and not dietary_ok:
            missing = [d for d in wanted_dietary if d not in dietary]
            soft_mismatches.append("dietary: " + "+".join(missing))
        if wanted_cuisines and not cuisine_ok:
            soft_mismatches.append("cuisine: " + "/".join(wanted_cuisines))
        soft_mismatches.extend(pref["mismatches"])

        raw_bm25 = bm25(query_terms, index["docs"][idx], index)

        scored.append(
            {
                "restaurant": r,
                "score": score,
                "reasons": reasons,
                "soft_ok": soft_ok,
                "dietary_ok": dietary_ok,
                "cuisine_ok": cuisine_ok,
                "preference_ok": preference_ok,
                "raw_bm25": raw_bm25,
                "soft_mismatches": soft_mismatches,
            }
        )

    # Normalize BM25 to a 0-8 bonus so it complements (not dominates) quality,
    # distance, hard-constraint and structured-preference signals.
    max_bm25 = max((c["raw_bm25"] for c in scored), default=0.0)
    if max_bm25 > 0:
        for c in scored:
            lexical = 8.0 * c["raw_bm25"] / max_bm25
            c["score"] += round(lexical, 2)
            c["lexical_score"] = round(lexical, 2)

    scored.sort(key=lambda x: (-x["score"], -x["restaurant"].get("rating", 0)))
    return scored


def split_soft_matches(
    scored: list[dict], p: ParseResult
) -> tuple[list[dict], dict]:
    """Strict soft matches when available; otherwise hard-only fallback.

    When at least one restaurant satisfies every hard constraint and every soft
    preference, only those restaurants are returned. If none do, the hard-only
    matches are returned as a disclosed fallback.
    """
    if not scored:
        return [], {"soft_fallback": False, "unmet_soft": []}

    strict = [s for s in scored if s["soft_ok"]]
    if strict:
        return strict, {"soft_fallback": False, "unmet_soft": []}

    fallback = sorted(
        scored,
        key=lambda s: (
            -(
                int(s["dietary_ok"])
                + int(s["cuisine_ok"])
                + int(s["preference_ok"])
            ),
            -s["score"],
            -s["restaurant"].get("rating", 0),
        ),
    )
    requested = []
    if p.dietary:
        requested.append("dietary")
    if p.cuisines:
        requested.append("cuisines")
    if p.dish_intent or p.texture or p.vibe:
        requested.append("preferences")
    return fallback, {"soft_fallback": True, "unmet_soft": requested}


def search_ranked_pool(
    restaurants: Iterable[dict], p: ParseResult, pool_limit: int
) -> tuple[list[dict], dict, ParseResult, list[str]]:
    """Rank with strict/fallback semantics, but let food-type intent outrank price.

    If a cuisine/dish/texture/vibe request cannot be satisfied inside the
    requested price band, try relaxing only the price filter. If that produces a
    strict soft match, return it and disclose the price relaxation. Safety and
    logistics constraints (allergens, meal, time, avoid) are never relaxed here.

    Returns up to `pool_limit` deterministically ordered candidates (the
    candidate set the constrained LLM re-ranker may choose from), plus the soft
    metadata, the effective parse, and the relaxed fields.
    """
    restaurants = list(restaurants)
    scored = filter_and_score(restaurants, p)
    selected, meta = split_soft_matches(scored, p)
    effective = p
    relaxed: list[str] = []

    has_food_type = bool(p.cuisines or p.dish_intent or p.texture or p.vibe)
    if p.price_level and has_food_type and (not selected or meta["soft_fallback"]):
        price_relaxed = p.model_copy(deep=True)
        price_relaxed.price_level = None
        relaxed_scored = filter_and_score(restaurants, price_relaxed)
        relaxed_selected, relaxed_meta = split_soft_matches(
            relaxed_scored, price_relaxed
        )
        if relaxed_selected and not relaxed_meta["soft_fallback"]:
            selected, meta = relaxed_selected, relaxed_meta
            effective = price_relaxed
            relaxed = ["price_level"]

    return selected[:pool_limit], meta, effective, relaxed


def search_ranked(
    restaurants: Iterable[dict], p: ParseResult, limit: int
) -> tuple[list[dict], dict, ParseResult, list[str]]:
    """Ranking entry point returning at most `limit` picks.

    Thin wrapper over `search_ranked_pool`; the chat pipeline uses the pool
    variant so the constrained LLM re-ranker can choose from top-K candidates.
    """
    return search_ranked_pool(restaurants, p, limit)


def card(restaurant: dict, reason: str = "") -> dict:
    """Compact restaurant card for chat responses (keep payload small)."""
    return {
        "id": restaurant["id"],
        "name": restaurant["name"],
        "cuisine": restaurant["cuisine"],
        "cuisine_tags": restaurant.get("cuisine_tags", []),
        "price_level": restaurant.get("price_level"),
        "price_symbol": PRICE_SYMBOL.get(restaurant.get("price_level"), ""),
        "avg_cost": restaurant.get("avg_cost"),
        "rating": restaurant.get("rating"),
        "review_count": restaurant.get("review_count"),
        "area": restaurant.get("area"),
        "address": restaurant.get("address"),
        "lat": restaurant.get("lat"),
        "lng": restaurant.get("lng"),
        "walk_minutes": restaurant.get("walk_minutes"),
        "hero_image": restaurant.get("hero_image", ""),
        "tags": restaurant.get("tags", []),
        "preference_tags": normalize_preference_tags(
            restaurant.get("preference_tags") or []
        ),
        "allergens": sorted(detect_allergens(restaurant)),
        "reason": reason,
    }
