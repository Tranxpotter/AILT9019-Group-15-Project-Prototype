"""Structured parsing of a chat message into filters.

Primary path: ask the configured LLM to emit strict JSON matching PARSE_SCHEMA.
Fallback (no LLM configured, or parse failure): deterministic keyword parser so
the app stays fully usable in demo mode.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from ..config import CUISINES, DIETARY_OPTIONS, MEALS
from ..schemas import ParseResult
from .providers import LLMError, get_provider

PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "meal": {"type": "string", "enum": MEALS, "description": "Which meal the user plans to eat, or omit if unknown"},
        "cuisines": {"type": "array", "items": {"type": "string"}, "description": "Cuisines the user wants, e.g. Candle, Noodles, Japanese, Thai, Desserts, Indian..."},
        "price_level": {"type": "integer", "enum": [1, 2, 3], "description": "1 = cheap ($), 2 = mid ($$), 3 = expensive ($$$). Omit if not mentioned"},
        "open_at": {"type": "string", "description": "24h 'HH:MM' when the user will eat, e.g. '13:30'. Omit if unknown"},
        "dietary": {"type": "array", "items": {"type": "string", "enum": DIETARY_OPTIONS}, "description": "Required dietary standards"},
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "3-6 short keywords: dish names, vibes, features (e.g. 'wonton', 'soup', 'waterfront', 'late night', 'quiet')"},
        "avoid": {"type": "array", "items": {"type": "string"}, "description": "Features/dish names to explicitly avoid"},
        "notes": {"type": "string", "description": "One short sentence summarising the user's intent"},
    },
    "required": ["meal", "cuisines", "price_level", "open_at", "dietary", "keywords", "avoid", "notes"],
}

PARSE_SYSTEM = (
    "You extract structured restaurant-search filters from a user's natural-language message. "
    "Reply with ONLY a JSON object conforming exactly to the given schema. "
    "Use null/empty arrays when information is absent. Do not invent data. "
    "Use US cents-free short English strings. The user is a university student near HKU, Hong Kong. "
    "If the user says 'cheap/budget' use price_level 1; 'expensive/fancy/upscale' use 3; otherwise omit."
)


def parse_with_llm(config: dict, message: str) -> ParseResult:
    provider = get_provider(config)
    if provider is None:
        raise LLMError("No LLM configured")
    user = (
        "Extract filters from this message. Respond with JSON only.\n"
        f'<message>{message}</message>\n'
        f'<schema>{PARSE_SCHEMA}</schema>'
    )
    data = provider.chat_json(PARSE_SYSTEM, user, PARSE_SCHEMA, max_tokens=600)
    return _validate(data, message)


def _validate(data: dict, message: str) -> ParseResult:
    data = data or {}
    return ParseResult(
        meal=(data.get("meal") or None),
        cuisines=[str(c) for c in (data.get("cuisines") or [])],
        price_level=(data.get("price_level") or None),
        open_at=(data.get("open_at") or None),
        dietary=[str(d) for d in (data.get("dietary") or [])],
        keywords=[str(k) for k in (data.get("keywords") or [])],
        avoid=[str(a) for a in (data.get("avoid") or [])],
        notes=str(data.get("notes") or ""),
    )


# ---------------------------------------------------------------- fallback ----

MEAL_WORDS = {
    "breakfast": ["breakfast", "morning", "brunch", "早", "eggs", "coffee in the morning"],
    "lunch": ["lunch", "noon", "midday", "afternoon", "12", "1pm", "2pm"],
    "dinner": ["dinner", "evening", "night", "supper", "6pm", "7pm", "8pm", "9pm"],
    "snack": ["snack", "dessert", "sweet", "late night", "midnight"],
}
PRICE_WORDS = {
    1: ["cheap", "budget", "affordable", "cheapest", "cheap eat", "student price", "inexpensive", "便宜"],
    3: ["expensive", "fancy", "upscale", "date night", "high-end", "splurge"],
}
DIET_WORDS = {
    "vegetarian": ["vegetarian", "veggie", "no meat", "vegan"],
    "vegan": ["vegan"],
    "halal": ["halal"],
    "no-pork": ["no pork", "don't eat pork", "not eat pork"],
    "gluten-free": ["gluten free", "gluten-free", "glutenfree"],
    "nut-free": ["nut free", "nut-free", "peanut allergy", "allergic to nuts"],
}
CUISINE_WORDS = {
    "Cantonese": ["cantonese", "hong kong"],
    "Dim Sum": ["dim sum", "yum cha", "dumpling"],
    "Noodles": ["noodle", "noodles", "wonton", "ramen"],
    "Western": ["western", "brunch", "burger", "coffee", "cafe"],
    "Indian": ["indian", "curry"],
    "Nepalese": ["nepalese"],
    "Thai": ["thai"],
    "Japanese": ["japanese", "sushi", "japanese"],
    "Healthy": ["healthy", "salad", "salad bar", "bowl", "grain bowl"],
    "Vegetarian": ["vegetarian"],
    "Desserts": ["dessert", "dessert", "sweet", "mango sago"],
    "Burgers": ["burger", "burgers", "steak"],
}


def _hhmm_to_min(hhmm: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm or "")
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_demo(message: str) -> ParseResult:
    """Deterministic keyword parser — no external calls."""
    msg = message.lower()
    meal = None
    for name, words in MEAL_WORDS.items():
        if any(w in msg for w in words):
            meal = name
            break
    cuisines = [c for c, words in CUISINE_WORDS.items() if any(w in msg for w in words)]
    price_level = None
    if any(w in msg for w in PRICE_WORDS[1]):
        price_level = 1
    if any(w in msg for w in PRICE_WORDS[3]):
        price_level = 3
    dietary = [d for d, words in DIET_WORDS.items() if any(w in msg for w in words)]
    # dedupe within diet words check ordering
    dietary = list(dict.fromkeys(dietary))

    open_at = None
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", msg)
    if m:
        open_at = f"{int(m.group(1)):02d}:{m.group(2)}"
    elif "night" in msg or "evening" in msg:
        open_at = "19:00"

    keywords = []
    for w in re.findall(r"[a-zA-Z]{4,}", message.lower()):
        if w not in ("breakfast", "lunch", "dinner", "snack", "cheap", "budget", "expensive", "fancy", "restaurant", "please", "around", "near", "campus", "university", "want", "some"):
            keywords.append(w)
    keywords = keywords[:6]
    avoid = []
    if "no pork" in msg:
        avoid.append("pork")
    if "not spicy" in msg or "no spicy" in msg:
        avoid.append("spicy")

    return ParseResult(
        meal=meal,
        cuisines=cuisines,
        price_level=price_level,
        open_at=open_at,
        dietary=dietary,
        keywords=keywords,
        avoid=avoid,
        notes="parsed by built-in keyword parser (demo mode)",
    )


def parse_message(config: dict, message: str) -> tuple[ParseResult, str]:
    """Returns (parse, mode). Falls back to demo parsing on any failure."""
    if not message.strip():
        return ParseResult(), "demo"
    try:
        return parse_with_llm(config, message), "llm"
    except Exception:
        return parse_demo(message), "demo"
