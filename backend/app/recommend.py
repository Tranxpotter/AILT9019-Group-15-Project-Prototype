"""Deterministic filtering + scoring over the restaurant dataset.

The LLM (or keyword parser) only produces structured filters; the ranking logic
lives here so recommendations are reproducible and testable.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .schemas import ParseResult

PRICE_SYMBOL = {1: "$", 2: "$$", 3: "$$$"}


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


def filter_and_score(
    restaurants: Iterable[dict],
    p: ParseResult,
    exclude_ids: Optional[set[str]] = None,
) -> list[dict]:
    """Return restaurants sorted by score with a `matched` reason list."""
    exclude_ids = exclude_ids or set()
    meal = (p.meal or "").strip().lower() or None
    price = p.price_level
    open_at = (p.open_at or "").strip()
    time_min: Optional[int] = None
    if open_at:
        try:
            time_min = int(open_at[:2]) * 60 + int(open_at[3:5])
        except (ValueError, TypeError):
            time_min = None

    scored = []
    for r in restaurants:
        if r["id"] in exclude_ids:
            continue
        # hard constraints
        if meal and meal not in (r.get("meal_categories") or []):
            continue
        if price and r.get("price_level") != price:
            continue
        if time_min is not None and not _open_at(r, time_min):
            continue
        dietary = r.get("dietary") or []
        if any(d not in dietary for d in (p.dietary or [])):
            continue

        hay = _text_haystack(r)
        if p.avoid:
            if any(a.lower() in hay for a in p.avoid if a):
                continue

        score = round(r.get("rating", 0) * 10, 1)
        reasons = []
        if meal:
            score += 8
            reasons.append(f"serves {meal}")
        cuisines = [c for c in (p.cuisines or []) if c]
        hit_cuisine = [c for c in cuisines if c.lower() in hay]
        if cuisines and hit_cuisine:
            score += 6
            reasons.append(",".join(hit_cuisine[:2]).title())
        if price:
            reasons.append(f"~{PRICE_SYMBOL.get(price, '')}")
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
        scored.append({"restaurant": r, "score": score, "reasons": reasons})

    scored.sort(key=lambda x: (-x["score"], -x["restaurant"].get("rating", 0)))
    return scored


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
        "reason": reason,
    }
