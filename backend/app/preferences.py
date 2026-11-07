"""Preference ontology + deterministic extraction.

Preferences are richer than cuisine/dietary labels: they describe the *kind of
food* (soup noodles, ramen, sashimi), its *texture* (soup, wet, grilled,
spicy), and the *vibe/occasion* (comforting, quick, quiet, late-night).

The LLM may extract preferences, but this module normalizes them to canonical
tags and provides a deterministic fallback so explicit phrases are never lost.
"""
from __future__ import annotations

import re
from typing import Iterable

PREFERENCE_CATEGORIES: dict[str, list[str]] = {
    "dish_intent": [
        "soup noodles",
        "wonton",
        "ramen",
        "udon",
        "pad thai",
        "tom yum",
        "sashimi",
        "grain bowl",
        "rice bowl",
    ],
    "texture": [
        "soup",
        "broth",
        "wet",
        "dry",
        "crispy",
        "grilled",
        "fried",
        "steamed",
        "raw",
        "cold",
        "hot",
        "spicy",
    ],
    "vibe": [
        "comforting",
        "hearty",
        "light",
        "fresh",
        "quick",
        "quiet",
        "group-friendly",
        "date-night",
        "late-night",
        "casual",
    ],
}

# Canonical tag -> user phrases. Pure cuisine/dietary/price words (noodles,
# sushi, curry, dessert, healthy, budget, ...) are intentionally excluded here;
# they are handled by the cuisine/price/dietary layers.
PREFERENCE_SYNONYMS: dict[str, list[str]] = {
    "soup noodles": ["soup noodles", "noodle soup", "noodles in soup", "wet noodles"],
    "wonton": ["wonton", "wontons"],
    "ramen": ["ramen"],
    "udon": ["udon"],
    "pad thai": ["pad thai"],
    "tom yum": ["tom yum"],
    "sashimi": ["sashimi", "raw fish", "raw seafood"],
    "grain bowl": ["grain bowl", "grain bowls"],
    "rice bowl": ["rice bowl", "rice bowls"],
    "soup": ["soup", "soupy", "brothy"],
    "broth": ["broth", "clear broth"],
    "wet": ["wet", "wet food", "slurpy", "slurp"],
    "dry": ["dry", "dry noodles", "stir-fried", "stir fried"],
    "crispy": ["crispy", "crunchy"],
    "grilled": ["grilled", "grill", "charcoal", "bbq", "barbecue"],
    "fried": ["fried", "deep-fried", "deep fried"],
    "steamed": ["steamed", "steam"],
    "raw": ["raw"],
    "cold": ["cold", "chilled"],
    "hot": ["hot", "piping hot"],
    "spicy": ["spicy", "spice", "chili", "chilli", "hot and spicy"],
    "comforting": ["comforting", "comfort food", "cozy", "cosy", "warm"],
    "hearty": ["hearty", "filling", "substantial"],
    "light": ["light", "not too heavy", "easy"],
    "fresh": ["fresh", "refreshing"],
    "quick": ["quick", "fast", "grab and go", "grab-and-go", "takeaway"],
    "quiet": ["quiet", "calm", "peaceful"],
    "group-friendly": ["group", "groups", "friends", "sharing", "group-friendly"],
    "date-night": ["date night", "date-night", "romantic"],
    "late-night": ["late night", "late-night", "midnight", "open late"],
    "casual": ["casual", "relaxed"],
}

_COMPOUND_TEXTURES: dict[str, set[str]] = {
    "soup noodles": {"soup", "wet"},
    "wonton": {"soup"},
    "ramen": {"soup"},
    "udon": {"soup"},
    "tom yum": {"soup"},
    "pad thai": {"dry"},
    "sashimi": {"raw"},
}


def _phrase_in_text(text: str, phrase: str) -> bool:
    return bool(
        re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text.lower())
    )


def _apply_compound_textures(result: dict[str, set[str]]) -> None:
    for dish, textures in _COMPOUND_TEXTURES.items():
        if dish in result["dish_intent"]:
            result["texture"].update(textures)


def extract_preferences(message: str) -> dict[str, list[str]]:
    """Deterministically extract preference tags from explicit user phrases."""
    text = (message or "").lower()
    result: dict[str, set[str]] = {k: set() for k in PREFERENCE_CATEGORIES}
    for category, tags in PREFERENCE_CATEGORIES.items():
        for tag in tags:
            phrases = PREFERENCE_SYNONYMS.get(tag, [tag])
            if any(_phrase_in_text(text, p) for p in phrases):
                result[category].add(tag)
    _apply_compound_textures(result)
    return {k: sorted(v) for k, v in result.items()}


def _match_tag(item: str, category: str) -> str | None:
    key = str(item).strip().lower()
    if not key:
        return None
    canonical = set(PREFERENCE_CATEGORIES[category])
    if key in canonical:
        return key
    for tag in canonical:
        for phrase in PREFERENCE_SYNONYMS.get(tag, [tag]):
            if _phrase_in_text(key, phrase):
                return tag
    return None


def normalize_preferences(
    data: dict[str, Iterable[str]] | None,
) -> dict[str, list[str]]:
    """Normalize LLM-provided preference lists to canonical tags."""
    data = data or {}
    result: dict[str, set[str]] = {k: set() for k in PREFERENCE_CATEGORIES}
    for category in PREFERENCE_CATEGORIES:
        for item in data.get(category) or []:
            tag = _match_tag(item, category)
            if tag:
                result[category].add(tag)
    _apply_compound_textures(result)
    return {k: sorted(v) for k, v in result.items()}


def normalize_preference_tags(tags: Iterable[str] | None) -> list[str]:
    """Normalize explicit restaurant preference tags to canonical tags."""
    out: set[str] = set()
    for tag in tags or []:
        for category, canonical in PREFERENCE_CATEGORIES.items():
            matched = _match_tag(tag, category)
            if matched:
                out.add(matched)
    return sorted(out)


def restaurant_preference_tags(restaurant: dict) -> dict[str, set[str]]:
    """Return the venue's canonical preference tags, grouped by category."""
    tags = set(normalize_preference_tags(restaurant.get("preference_tags") or []))
    return {
        "dish_intent": tags & set(PREFERENCE_CATEGORIES["dish_intent"]),
        "texture": tags & set(PREFERENCE_CATEGORIES["texture"]),
        "vibe": tags & set(PREFERENCE_CATEGORIES["vibe"]),
        "all": tags,
    }


def match_preferences(restaurant: dict, p) -> dict:
    """Check whether a venue matches each requested preference category."""
    tags = restaurant_preference_tags(restaurant)
    wanted = {
        "dish_intent": [t for t in (p.dish_intent or []) if t],
        "texture": [t for t in (p.texture or []) if t],
        "vibe": [t for t in (p.vibe or []) if t],
    }
    matched: list[str] = []
    mismatches: list[str] = []
    category_ok: dict[str, bool] = {}
    for category in ("dish_intent", "texture", "vibe"):
        requested = wanted[category]
        if not requested:
            category_ok[category] = True
            continue
        hit = bool(set(requested) & tags[category])
        category_ok[category] = hit
        label = "dish" if category == "dish_intent" else category
        if hit:
            matched.append(label + ": " + "/".join(requested))
        else:
            mismatches.append(label + ": " + "/".join(requested))
    return {
        "ok": all(category_ok.values()),
        "dish_intent_ok": category_ok["dish_intent"],
        "texture_ok": category_ok["texture"],
        "vibe_ok": category_ok["vibe"],
        "matched": matched,
        "mismatches": mismatches,
    }
