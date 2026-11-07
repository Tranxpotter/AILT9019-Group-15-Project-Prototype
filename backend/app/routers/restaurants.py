"""REST endpoints for restaurant data + explore/filter mode (no chat needed)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..allergens import (
    ALLERGEN_FILTER_LABELS,
    ALLERGEN_FILTER_OPTIONS,
    ALLERGEN_GROUPS,
    normalize_allergens,
)
from ..preferences import PREFERENCE_CATEGORIES, normalize_preferences
from ..recommend import PRICE_SYMBOL, card, search_ranked
from ..schemas import ParseResult

router = APIRouter(prefix="/api", tags=["restaurants"])

HUK_CENTER = {"lat": 22.2840, "lng": 114.1355}


def _as_str(value) -> str:
    return value if isinstance(value, str) else ""


def _as_int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _csv(value) -> list[str]:
    return [x.strip() for x in _as_str(value).split(",") if x.strip()]


def _parse_from_query(
    meal: Optional[str],
    cuisine: Optional[str],
    price_level: Optional[int],
    dietary: Optional[str],
    allergens: Optional[str],
    dish_intent: Optional[str],
    texture: Optional[str],
    vibe: Optional[str],
    open_at: Optional[str],
    q: Optional[str],
) -> ParseResult:
    prefs = normalize_preferences(
        {
            "dish_intent": _csv(dish_intent),
            "texture": _csv(texture),
            "vibe": _csv(vibe),
        }
    )
    return ParseResult(
        meal=_as_str(meal) or None,
        cuisines=_csv(cuisine),
        dish_intent=prefs["dish_intent"],
        texture=prefs["texture"],
        vibe=prefs["vibe"],
        price_level=_as_int(price_level),
        open_at=_as_str(open_at) or None,
        dietary=_csv(dietary),
        allergens=normalize_allergens(_csv(allergens)),
        keywords=[_as_str(q)] if _as_str(q) else [],
        avoid=[],
        notes="",
    )


@router.get("/restaurants")
def list_restaurants(
    meal: Optional[str] = Query(None),
    cuisine: Optional[str] = Query(None),
    price_level: Optional[int] = Query(None, ge=1, le=3),
    dietary: Optional[str] = Query(None),
    allergens: Optional[str] = Query(None),
    dish_intent: Optional[str] = Query(None),
    texture: Optional[str] = Query(None),
    vibe: Optional[str] = Query(None),
    open_at: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    p = _parse_from_query(
        meal,
        cuisine,
        price_level,
        dietary,
        allergens,
        dish_intent,
        texture,
        vibe,
        open_at,
        q,
    )
    selected, soft_meta, _effective, relaxed = search_ranked(
        db.list_restaurants(), p, limit
    )
    top = selected
    out = []
    for s in top:
        c = card(s["restaurant"], "; ".join(s["reasons"]))
        c["matched"] = s["reasons"]
        c["soft_mismatches"] = s.get("soft_mismatches", [])
        out.append(c)
    status = (
        "relaxed"
        if relaxed
        else ("soft_fallback" if soft_meta["soft_fallback"] else "ok")
    )
    return {
        "count": len(out),
        "items": out,
        "status": status,
        "soft_fallback": soft_meta["soft_fallback"],
        "unmet_soft": soft_meta["unmet_soft"],
        "relaxed": relaxed,
    }


@router.get("/restaurants/{restaurant_id}")
def restaurant_detail(restaurant_id: str):
    r = db.get_restaurant(restaurant_id)
    if not r:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    r["images"] = {
        "hero": r["hero_image"],
        "interior": r["interior_image"],
        "menu": r["menu_image"],
    }
    r["price_symbol"] = PRICE_SYMBOL.get(r["price_level"], "")
    return r


@router.get("/meta")
def meta():
    restaurants = db.list_restaurants()
    cuisines = sorted({r["cuisine"] for r in restaurants})
    tags = sorted({t for r in restaurants for t in (r.get("tags") or [])})
    return {
        "center": HUK_CENTER,
        "meals": ["breakfast", "lunch", "dinner", "snack"],
        "cuisines": cuisines,
        "all_cuisines": [
            "Cantonese", "Dim Sum", "Noodles", "Western", "Indian", "Thai",
            "Japanese", "Healthy", "Vegetarian", "Desserts", "Burgers",
        ],
        "tags": tags,
        "dietary_options": [
            "vegetarian", "vegan", "halal", "no-pork", "gluten-free", "nut-free",
        ],
        "dietary_labels": {
            "vegetarian": "Vegetarian",
            "vegan": "Vegan",
            "halal": "Halal",
            "no-pork": "No pork",
            "gluten-free": "Gluten-free kitchen",
            "nut-free": "Nut-free kitchen",
        },
        "allergen_options": ALLERGEN_FILTER_OPTIONS,
        "allergen_option_labels": ALLERGEN_FILTER_LABELS,
        "allergen_groups": ALLERGEN_GROUPS,
        "preference_options": PREFERENCE_CATEGORIES,
        "preference_labels": {
            "dish_intent": "Dish",
            "texture": "Texture",
            "vibe": "Vibe",
        },
        "price_levels": [{"level": 1, "symbol": "$"}, {"level": 2, "symbol": "$$"}, {"level": 3, "symbol": "$$$"}],
        "restaurants_count": len(restaurants),
    }
