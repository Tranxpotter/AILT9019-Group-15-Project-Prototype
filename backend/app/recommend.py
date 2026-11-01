"""Deterministic filtering + scoring over the restaurant dataset.

The LLM (or keyword parser) only produces structured filters; the ranking logic
lives here so recommendations are reproducible and testable.
"""
from __future__ import annotations

from typing import Iterable

from .allergens import detect_allergens
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


def filter_and_score(restaurants: Iterable[dict], p: ParseResult) -> list[dict]:
    """Return all hard-constraint matches, scored and annotated with soft flags.

    Hard constraints: meal, price, open_at, allergens, avoid.
    Soft preferences: dietary, cuisines. Keywords remain ranking signals only.
    """
    meal = (p.meal or "").strip().lower() or None
    price = p.price_level
    open_at = (p.open_at or "").strip()
    time_min: int | None = None
    if open_at:
        try:
            time_min = int(open_at[:2]) * 60 + int(open_at[3:5])
        except (ValueError, TypeError):
            time_min = None

    wanted_allergens = set(p.allergens or [])
    wanted_dietary = [d for d in (p.dietary or []) if d]
    wanted_cuisines = [c for c in (p.cuisines or []) if c]

    scored = []
    for r in restaurants:
        # Hard constraints
        if meal and meal not in (r.get("meal_categories") or []):
            continue
        # Full meals should not return dessert/snack venues.
        if meal in FULL_MEALS and _is_snack_venue(r):
            continue
        if price and r.get("price_level") != price:
            continue
        if time_min is not None and not _open_at(r, time_min):
            continue
        # Safety-critical: never return a venue that may contain a requested allergen.
        if wanted_allergens and wanted_allergens & detect_allergens(r):
            continue

        hay = _text_haystack(r)
        if p.avoid:
            if any(a.lower() in hay for a in p.avoid if a):
                continue

        # Soft preferences
        dietary = r.get("dietary") or []
        dietary_ok = all(d in dietary for d in wanted_dietary)
        cuisine_ok = _cuisine_match(r, wanted_cuisines)
        soft_ok = dietary_ok and cuisine_ok

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

        scored.append(
            {
                "restaurant": r,
                "score": score,
                "reasons": reasons,
                "soft_ok": soft_ok,
                "dietary_ok": dietary_ok,
                "cuisine_ok": cuisine_ok,
                "soft_mismatches": soft_mismatches,
            }
        )

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
            -(int(s["dietary_ok"]) + int(s["cuisine_ok"])),
            -s["score"],
            -s["restaurant"].get("rating", 0),
        ),
    )
    requested = []
    if p.dietary:
        requested.append("dietary")
    if p.cuisines:
        requested.append("cuisines")
    return fallback, {"soft_fallback": True, "unmet_soft": requested}


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
        "allergens": sorted(detect_allergens(restaurant)),
        "reason": reason,
    }
