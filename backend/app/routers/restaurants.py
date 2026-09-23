"""REST endpoints for restaurant data + explore/filter mode (no chat needed)."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..recommend import PRICE_SYMBOL, card, filter_and_score
from ..schemas import ParseResult

router = APIRouter(prefix="/api", tags=["restaurants"])

HUK_CENTER = {"lat": 22.2840, "lng": 114.1355}


def _parse_from_query(
    meal: Optional[str],
    cuisine: Optional[str],
    price_level: Optional[int],
    dietary: Optional[str],
    open_at: Optional[str],
    q: Optional[str],
) -> ParseResult:
    return ParseResult(
        meal=meal or None,
        cuisines=[c for c in (cuisine or "").split(",") if c],
        price_level=price_level,
        open_at=open_at or None,
        dietary=[d for d in (dietary or "").split(",") if d],
        keywords=[q] if q else [],
        avoid=[],
        notes="",
    )


@router.get("/restaurants")
def list_restaurants(
    meal: Optional[str] = Query(None),
    cuisine: Optional[str] = Query(None),
    price_level: Optional[int] = Query(None, ge=1, le=3),
    dietary: Optional[str] = Query(None),
    open_at: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    exclude_previous: bool = Query(False),
    limit: int = Query(10, ge=1, le=50),
):
    p = _parse_from_query(meal, cuisine, price_level, dietary, open_at, q)
    exclude = db.suggested_restaurant_ids(50) if exclude_previous else set()
    scored = filter_and_score(db.list_restaurants(), p, exclude)
    top = scored[:limit]
    out = []
    for s in top:
        c = card(s["restaurant"], "; ".join(s["reasons"]))
        c["matched"] = s["reasons"]
        out.append(c)
    return {"count": len(out), "items": out}


@router.get("/restaurants/{restaurant_id}")
def restaurant_detail(restaurant_id: str):
    r = db.get_restaurant(restaurant_id)
    if not r:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    r["user_review"] = db.get_user_review(restaurant_id)
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
        "price_levels": [{"level": 1, "symbol": "$"}, {"level": 2, "symbol": "$$"}, {"level": 3, "symbol": "$$$"}],
        "restaurants_count": len(restaurants),
    }
