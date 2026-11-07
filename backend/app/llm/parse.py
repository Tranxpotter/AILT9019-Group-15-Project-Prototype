"""Structured parsing of a chat message into filters.

Primary path: ask the configured LLM to emit strict JSON matching PARSE_SCHEMA.
Fallback (no LLM configured, or parse failure): deterministic keyword parser so
the app stays fully usable in demo mode.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from ..allergens import (
    ALLERGEN_SCHEMA_OPTIONS,
    extract_allergens,
    has_allergy_framing,
    normalize_allergens,
)
from ..config import CUISINES, DIETARY_OPTIONS, MEALS
from ..preferences import extract_preferences, normalize_preferences
from ..schemas import ParseResult
from .providers import LLMError, get_provider

PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "meal": {"type": "string", "enum": MEALS, "description": "Which meal the user plans to eat, or omit if unknown"},
        "cuisines": {"type": "array", "items": {"type": "string"}, "description": "Cuisines the user wants, e.g. Candle, Noodles, Japanese, Thai, Desserts, Indian..."},
        "dish_intent": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Dish-level intent, e.g. soup noodles, wonton, ramen, udon, pad thai, tom yum, sashimi, grain bowl. Do not duplicate pure cuisine words.",
        },
        "texture": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Texture/style, e.g. soup, wet, dry, grilled, spicy, crispy, steamed, raw.",
        },
        "vibe": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Vibe/occasion, e.g. comforting, light, quick, quiet, group-friendly, date-night, late-night.",
        },
        "price_level": {"type": "integer", "enum": [1, 2, 3], "description": "1 = cheap ($), 2 = mid ($$), 3 = expensive ($$$). Omit if not mentioned"},
        "open_at": {"type": "string", "description": "24h 'HH:MM' when the user will eat, e.g. '13:30'. Omit if unknown"},
        "dietary": {"type": "array", "items": {"type": "string", "enum": DIETARY_OPTIONS}, "description": "Required dietary standards"},
        "allergens": {
            "type": "array",
            "items": {"type": "string", "enum": ALLERGEN_SCHEMA_OPTIONS},
            "description": "Safety-critical allergens to exclude. Use 'seafood' for a seafood allergy, 'shellfish' for shellfish, or a specific group. Never omit an allergy mentioned by the user.",
        },
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "3-6 short keywords: dish names, vibes, features (e.g. 'wonton', 'soup', 'waterfront', 'late night', 'quiet')"},
        "avoid": {"type": "array", "items": {"type": "string"}, "description": "Features/dish names to explicitly avoid"},
        "notes": {"type": "string", "description": "One short sentence summarising the user's intent"},
    },
    "required": ["meal", "cuisines", "dish_intent", "texture", "vibe", "price_level", "open_at", "dietary", "allergens", "keywords", "avoid", "notes"],
}

PARSE_SYSTEM = (
    "You extract structured restaurant-search filters from a user's natural-language message. "
    "Reply with ONLY a JSON object conforming exactly to the given schema. "
    "Use null/empty arrays when information is absent. Do not invent data. "
    "Use US cents-free short English strings. The user is a university student near HKU, Hong Kong. "
    "If the user says 'cheap/budget' use price_level 1; 'expensive/fancy/upscale' use 3; otherwise omit. "
    "Allergies are safety-critical: always put allergy/intolerance/avoidance terms (e.g. seafood, "
    "shellfish, peanut, tree-nut, gluten, dairy, egg, soy, sesame) in `allergens`, never in `dietary` "
    "and never only in `avoid`. `dietary` is for dietary preferences/certifications: vegetarian, vegan, "
    "halal, no-pork, gluten-free, nut-free. "
    "'No seafood' means allergens=['seafood']; 'shellfish allergy' means allergens=['shellfish']; "
    "'allergic to nuts' means allergens=['peanut','tree-nut'] with no dietary label; "
    "'nut-free'/'gluten-free' diet requests use `dietary`. "
    "Always extract cuisines from explicit dish/cuisine words: curry→Indian, sushi→Japanese, "
    "noodles→Noodles, dessert→Desserts, dim sum→Dim Sum, burger/steak→Burgers, "
    "salad/bowl→Healthy, coffee/brunch→Western. "
    "Also extract richer preferences: 'soup noodles'→dish_intent=['soup noodles'], "
    "texture=['soup','wet']; 'spicy'→texture=['spicy']; 'grilled'→texture=['grilled']; "
    "'comforting'→vibe=['comforting']; 'quick'→vibe=['quick']; 'late night'→vibe=['late-night']. "
    "Do not duplicate pure cuisine words (noodles, sushi, curry, dessert, healthy) in preferences."
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
    data = provider.chat_json(PARSE_SYSTEM, user, PARSE_SCHEMA, max_tokens=900)
    return _validate(data, message)


def _validate(data: dict, message: str) -> ParseResult:
    data = data or {}
    # Safety net: deterministically extract allergens from the message even
    # if the LLM omitted them, then union with whatever the LLM returned.
    allergens = normalize_allergens(
        list(data.get("allergens") or []) + extract_allergens(message)
    )
    dietary = list(
        dict.fromkeys(
            [str(d) for d in (data.get("dietary") or [])] + extract_dietary(message)
        )
    )
    # Reconcile LLM output: an allergy request should not also impose a
    # redundant dietary certification label unless the user explicitly asked
    # for that certification (e.g. "allergic to nuts, nut-free kitchen").
    if has_allergy_framing(message):
        msg = message.lower()
        if {"peanut", "tree-nut"} & set(allergens) and not re.search(
            r"\bnut[\s-]*free\b", msg
        ):
            dietary = [d for d in dietary if d != "nut-free"]
        if "gluten" in allergens and not re.search(r"\bgluten[\s-]*free\b", msg):
            dietary = [d for d in dietary if d != "gluten-free"]

    cuisines = [str(c) for c in (data.get("cuisines") or [])]
    # Deterministic enrichment: explicit dish/cuisine words (curry, sushi,
    # noodles, dessert, ...) must not be lost just because the LLM omitted them.
    cuisines = list(dict.fromkeys(cuisines + extract_cuisines(message)))
    # "Vegetarian" is a dataset cuisine label but is really a dietary preference.
    # When dietary already captures it, avoid double-constraining.
    if {"vegetarian", "vegan"} & set(dietary):
        cuisines = [c for c in cuisines if c.lower() != "vegetarian"]

    # Deterministic preference enrichment: explicit phrases (soup noodles,
    # spicy, grilled, comforting, ...) must not be lost just because the LLM
    # omitted them. Also inspect LLM keywords for preference phrases.
    msg_prefs = extract_preferences(message)
    kw_prefs = extract_preferences(
        " ".join(str(k) for k in (data.get("keywords") or []))
    )
    preferences = normalize_preferences(
        {
            "dish_intent": list(data.get("dish_intent") or [])
            + msg_prefs["dish_intent"]
            + kw_prefs["dish_intent"],
            "texture": list(data.get("texture") or [])
            + msg_prefs["texture"]
            + kw_prefs["texture"],
            "vibe": list(data.get("vibe") or [])
            + msg_prefs["vibe"]
            + kw_prefs["vibe"],
        }
    )

    return ParseResult(
        meal=(data.get("meal") or None),
        cuisines=cuisines,
        dish_intent=preferences["dish_intent"],
        texture=preferences["texture"],
        vibe=preferences["vibe"],
        price_level=(data.get("price_level") or None),
        open_at=(data.get("open_at") or None),
        dietary=dietary,
        allergens=allergens,
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
    # Dietary certifications only. Allergy phrasing (e.g. "peanut allergy",
    # "allergic to nuts") is handled by `extract_allergens` instead.
    "gluten-free": ["gluten free", "gluten-free", "glutenfree"],
    "nut-free": ["nut free", "nut-free"],
}
CUISINE_WORDS = {
    "Cantonese": ["cantonese", "hong kong"],
    "Dim Sum": ["dim sum", "yum cha", "dumpling"],
    "Noodles": ["noodle", "noodles", "wonton"],
    "Western": ["western", "brunch", "burger", "coffee", "cafe"],
    "Indian": ["indian", "curry"],
    "Nepalese": ["nepalese"],
    "Thai": ["thai"],
    "Japanese": ["japanese", "sushi", "ramen", "udon", "sashimi"],
    "Healthy": ["healthy", "salad", "salad bar", "bowl", "grain bowl"],
    "Vegetarian": ["vegetarian"],
    "Desserts": ["dessert", "dessert", "sweet", "mango sago"],
    "Burgers": ["burger", "burgers", "steak"],
}


def extract_cuisines(message: str) -> list[str]:
    """Deterministically extract cuisines from explicit dish/cuisine words."""
    msg = (message or "").lower()
    return list(
        dict.fromkeys(
            c for c, words in CUISINE_WORDS.items() if any(w in msg for w in words)
        )
    )


def extract_dietary(message: str) -> list[str]:
    """Deterministically extract dietary labels from explicit diet phrases."""
    msg = (message or "").lower()
    return list(
        dict.fromkeys(
            d for d, words in DIET_WORDS.items() if any(w in msg for w in words)
        )
    )


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
    cuisines = extract_cuisines(message)
    price_level = None
    if any(w in msg for w in PRICE_WORDS[1]):
        price_level = 1
    if any(w in msg for w in PRICE_WORDS[3]):
        price_level = 3
    dietary = extract_dietary(message)
    # "Vegetarian" is a cuisine label in the dataset but is really a dietary
    # preference. When dietary already captures it, avoid double-constraining.
    if {"vegetarian", "vegan"} & set(dietary):
        cuisines = [c for c in cuisines if c.lower() != "vegetarian"]

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

    prefs = extract_preferences(message)
    return ParseResult(
        meal=meal,
        cuisines=cuisines,
        dish_intent=prefs["dish_intent"],
        texture=prefs["texture"],
        vibe=prefs["vibe"],
        price_level=price_level,
        open_at=open_at,
        dietary=dietary,
        allergens=extract_allergens(message),
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
