"""Deterministic allergen taxonomy, extraction, and detection.

Allergies are safety-critical. The LLM may help extract them, but the backend
always normalizes and enforces them here. Restaurant allergen flags are
conservative: if any ingredient synonym is found in the venue's text (or the
venue carries an explicit allergen flag), the allergen is assumed present.

Canonical groups are stored in `ParseResult.allergens` and in the restaurant
DB. User-facing terms like "seafood" and "shellfish" expand to those groups.
"""
from __future__ import annotations

import re
from typing import Iterable

# Canonical allergen groups stored in ParseResult.allergens / DB.
ALLERGEN_GROUPS: dict[str, str] = {
    "fish": "Fish",
    "crustacean": "Crustaceans (prawn, shrimp, crab, lobster)",
    "mollusk": "Mollusks (oyster, clam, mussel, scallop, squid, octopus)",
    "peanut": "Peanuts",
    "tree-nut": "Tree nuts",
    "gluten": "Gluten / wheat",
    "dairy": "Dairy",
    "egg": "Egg",
    "soy": "Soy",
    "sesame": "Sesame",
}

# Short labels used in summaries/disclosures.
ALLERGEN_SHORT_LABELS: dict[str, str] = {
    "fish": "fish",
    "crustacean": "crustaceans",
    "mollusk": "mollusks",
    "peanut": "peanuts",
    "tree-nut": "tree nuts",
    "gluten": "gluten",
    "dairy": "dairy",
    "egg": "egg",
    "soy": "soy",
    "sesame": "sesame",
}

# User-facing quick-filter options. "seafood" and "shellfish" are groups that
# expand to canonical allergen groups.
ALLERGEN_FILTER_OPTIONS: list[str] = [
    "seafood",
    "fish",
    "shellfish",
    "peanut",
    "tree-nut",
    "gluten",
    "dairy",
    "egg",
    "soy",
    "sesame",
]

# Options exposed to the LLM parse schema. Includes the canonical shellfish
# sub-groups so a model can return precise values when the user names them.
ALLERGEN_SCHEMA_OPTIONS: list[str] = ALLERGEN_FILTER_OPTIONS + [
    "crustacean",
    "mollusk",
]

ALLERGEN_FILTER_LABELS: dict[str, str] = {
    "seafood": "Seafood",
    "fish": "Fish",
    "shellfish": "Shellfish",
    "peanut": "Peanut",
    "tree-nut": "Tree nut",
    "gluten": "Gluten",
    "dairy": "Dairy",
    "egg": "Egg",
    "soy": "Soy",
    "sesame": "Sesame",
}

# User phrase -> canonical group(s).
_USER_TERMS: dict[str, list[str]] = {
    "seafood": ["fish", "crustacean", "mollusk"],
    "shellfish": ["crustacean", "mollusk"],
    "fish": ["fish"],
    "crustacean": ["crustacean"],
    "crustaceans": ["crustacean"],
    "mollusk": ["mollusk"],
    "mollusks": ["mollusk"],
    "mollusc": ["mollusk"],
    "molluscs": ["mollusk"],
    "prawn": ["crustacean"],
    "prawns": ["crustacean"],
    "shrimp": ["crustacean"],
    "shrimps": ["crustacean"],
    "crab": ["crustacean"],
    "crabs": ["crustacean"],
    "lobster": ["crustacean"],
    "lobsters": ["crustacean"],
    "crayfish": ["crustacean"],
    "oyster": ["mollusk"],
    "oysters": ["mollusk"],
    "clam": ["mollusk"],
    "clams": ["mollusk"],
    "mussel": ["mollusk"],
    "mussels": ["mollusk"],
    "scallop": ["mollusk"],
    "scallops": ["mollusk"],
    "squid": ["mollusk"],
    "octopus": ["mollusk"],
    "abalone": ["mollusk"],
    "calamari": ["mollusk"],
    "peanut": ["peanut"],
    "peanuts": ["peanut"],
    "tree nut": ["tree-nut"],
    "tree nuts": ["tree-nut"],
    "treenut": ["tree-nut"],
    "treenuts": ["tree-nut"],
    "nut": ["tree-nut", "peanut"],
    "nuts": ["tree-nut", "peanut"],
    "almond": ["tree-nut"],
    "almonds": ["tree-nut"],
    "cashew": ["tree-nut"],
    "cashews": ["tree-nut"],
    "walnut": ["tree-nut"],
    "walnuts": ["tree-nut"],
    "pistachio": ["tree-nut"],
    "pistachios": ["tree-nut"],
    "hazelnut": ["tree-nut"],
    "hazelnuts": ["tree-nut"],
    "pecan": ["tree-nut"],
    "pecans": ["tree-nut"],
    "macadamia": ["tree-nut"],
    "pine nut": ["tree-nut"],
    "pine nuts": ["tree-nut"],
    "chestnut": ["tree-nut"],
    "chestnuts": ["tree-nut"],
    "gluten": ["gluten"],
    "wheat": ["gluten"],
    "celiac": ["gluten"],
    "coeliac": ["gluten"],
    "dairy": ["dairy"],
    "milk": ["dairy"],
    "lactose": ["dairy"],
    "egg": ["egg"],
    "eggs": ["egg"],
    "soy": ["soy"],
    "soya": ["soy"],
    "soybean": ["soy"],
    "soybeans": ["soy"],
    "sesame": ["sesame"],
    "tahini": ["sesame"],
}

# Ingredient terms scanned in restaurant text. Generic words like "gluten" and
# "dairy" are included but negation handling below prevents "gluten-free" /
# "dairy-free" from being treated as presence.
_INGREDIENT_TERMS: dict[str, list[str]] = {
    # Fish
    "fish": ["fish"],
    "salmon": ["fish"],
    "tuna": ["fish"],
    "cod": ["fish"],
    "anchovy": ["fish"],
    "anchovies": ["fish"],
    "toro": ["fish"],
    "sashimi": ["fish"],
    "chirashi": ["fish"],
    "mackerel": ["fish"],
    "bass": ["fish"],
    "snapper": ["fish"],
    "halibut": ["fish"],
    "trout": ["fish"],
    "eel": ["fish"],
    "unagi": ["fish"],
    "dashi": ["fish"],
    "bonito": ["fish"],
    "sardine": ["fish"],
    "sardines": ["fish"],
    "herring": ["fish"],
    "tilapia": ["fish"],
    "fish sauce": ["fish"],
    "fish market": ["fish"],
    # Crustaceans
    "prawn": ["crustacean"],
    "prawns": ["crustacean"],
    "shrimp": ["crustacean"],
    "shrimps": ["crustacean"],
    "crab": ["crustacean"],
    "crabs": ["crustacean"],
    "lobster": ["crustacean"],
    "lobsters": ["crustacean"],
    "crayfish": ["crustacean"],
    "langoustine": ["crustacean"],
    # Mollusks
    "oyster": ["mollusk"],
    "oysters": ["mollusk"],
    "clam": ["mollusk"],
    "clams": ["mollusk"],
    "mussel": ["mollusk"],
    "mussels": ["mollusk"],
    "scallop": ["mollusk"],
    "scallops": ["mollusk"],
    "squid": ["mollusk"],
    "octopus": ["mollusk"],
    "abalone": ["mollusk"],
    "calamari": ["mollusk"],
    "oyster sauce": ["mollusk"],
    # Peanut
    "peanut": ["peanut"],
    "peanuts": ["peanut"],
    "satay": ["peanut"],
    "peanut sauce": ["peanut"],
    # Tree nuts
    "almond": ["tree-nut"],
    "almonds": ["tree-nut"],
    "cashew": ["tree-nut"],
    "cashews": ["tree-nut"],
    "walnut": ["tree-nut"],
    "walnuts": ["tree-nut"],
    "pistachio": ["tree-nut"],
    "pistachios": ["tree-nut"],
    "hazelnut": ["tree-nut"],
    "hazelnuts": ["tree-nut"],
    "pecan": ["tree-nut"],
    "pecans": ["tree-nut"],
    "macadamia": ["tree-nut"],
    "pine nut": ["tree-nut"],
    "pine nuts": ["tree-nut"],
    "chestnut": ["tree-nut"],
    "chestnuts": ["tree-nut"],
    # Gluten / wheat
    "gluten": ["gluten"],
    "wheat": ["gluten"],
    "bread": ["gluten"],
    "sourdough": ["gluten"],
    "naan": ["gluten"],
    "pasta": ["gluten"],
    "ramen": ["gluten"],
    "udon": ["gluten"],
    "dumpling": ["gluten"],
    "dumplings": ["gluten"],
    "pancake": ["gluten"],
    "pancakes": ["gluten"],
    "pastry": ["gluten"],
    "cake": ["gluten"],
    "flour": ["gluten"],
    "couscous": ["gluten"],
    "barley": ["gluten"],
    "rye": ["gluten"],
    "seitan": ["gluten"],
    "panko": ["gluten"],
    "breadcrumb": ["gluten"],
    "breadcrumbs": ["gluten"],
    "burger": ["gluten"],
    "bun": ["gluten"],
    "spring roll": ["gluten"],
    "spring rolls": ["gluten"],
    "har gow": ["gluten"],
    "siu mai": ["gluten"],
    "tart": ["gluten"],
    # Dairy
    "milk": ["dairy"],
    "butter": ["dairy"],
    "cheese": ["dairy"],
    "cheddar": ["dairy"],
    "cream": ["dairy"],
    "yoghurt": ["dairy"],
    "yogurt": ["dairy"],
    "ice cream": ["dairy"],
    "ghee": ["dairy"],
    "paneer": ["dairy"],
    "latte": ["dairy"],
    "flat white": ["dairy"],
    "condensed milk": ["dairy"],
    # Egg
    "egg": ["egg"],
    "eggs": ["egg"],
    "mayonnaise": ["egg"],
    "mayo": ["egg"],
    "custard": ["egg"],
    "meringue": ["egg"],
    "aioli": ["egg"],
    "chawanmushi": ["egg"],
    # Soy
    "soy": ["soy"],
    "soya": ["soy"],
    "tofu": ["soy"],
    "edamame": ["soy"],
    "miso": ["soy"],
    "soy sauce": ["soy"],
    "tempeh": ["soy"],
    "tamari": ["soy"],
    # Sesame
    "sesame": ["sesame"],
    "tahini": ["sesame"],
    "hummus": ["sesame"],
    "halva": ["sesame"],
}

# Plant-based / non-dairy phrases that must not be flagged as dairy.
_DAIRY_EXCEPTIONS = (
    "soy milk",
    "soya milk",
    "almond milk",
    "coconut milk",
    "coconut cream",
    "oat milk",
    "rice milk",
    "cashew milk",
    "peanut butter",
    "almond butter",
    "cashew butter",
    "vegan cheese",
    "dairy-free",
    "non-dairy",
)

# "Water chestnut" is an aquatic vegetable, not a tree nut.
_TREE_NUT_EXCEPTIONS = (
    "water chestnut",
    "water chestnuts",
)

# Negation / absence context immediately before an ingredient term.
_NEGATION_BEFORE = re.compile(
    r"\b(?:no|without|free\s+(?:of|from)|not|avoid)\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)
_FREE_AFTER = re.compile(r"^\s*-?\s*free\b", re.IGNORECASE)

# Terms covered by a dietary option. "-free" phrasing for these is a dietary
# certification (venue label), not an allergen. Allergy phrasing for the same
# terms still maps to allergens.
DIETARY_FREE_TERMS = {"nut", "nuts", "gluten"}

# Triggers used to scan a clause for allergen terms in user messages. This
# catches lists such as "no seafood or shellfish" and "allergic to peanuts and
# prawns" even when the direct per-term patterns do not match the whole list.
_CLAUSE_TRIGGER = re.compile(
    r"\b(?:allergic\s+to|allergy\s+to|intolerance\s+to|can't\s+eat|cannot\s+eat|"
    r"can\s+not\s+eat|don't\s+eat|do\s+not\s+eat|avoid|no|without|free\s+of|free\s+from)\b",
    re.IGNORECASE,
)

# Allergy-specific framing (used to reconcile LLM output: an allergy should not
# also impose a redundant dietary certification label).
_ALLERGY_FRAMING = re.compile(
    r"\b(?:allergic\s+to|allergy|intolerance|intolerant|celiac|coeliac|"
    r"can't\s+eat|cannot\s+eat|can\s+not\s+eat|don't\s+eat|do\s+not\s+eat)\b",
    re.IGNORECASE,
)


def has_allergy_framing(message: str) -> bool:
    """True when the message describes an allergy/intolerance rather than a diet."""
    return bool(_ALLERGY_FRAMING.search(message or ""))


def normalize_allergens(items: Iterable[str] | None) -> list[str]:
    """Map user-facing allergen terms to sorted canonical groups."""
    out: set[str] = set()
    for item in items or []:
        key = str(item).strip().lower()
        if not key:
            continue
        if key in ALLERGEN_GROUPS:
            out.add(key)
        elif key in _USER_TERMS:
            out.update(_USER_TERMS[key])
    return sorted(out)


def allergens_from_terms(terms: Iterable[str] | None) -> list[str]:
    """Promote any allergen-like entries from `avoid`/UI terms to allergens."""
    out: set[str] = set()
    for term in terms or []:
        key = str(term).strip().lower()
        if not key:
            continue
        if key in ALLERGEN_GROUPS:
            out.add(key)
        elif key in _USER_TERMS:
            out.update(_USER_TERMS[key])
        else:
            out.update(extract_allergens(key))
    return sorted(out)


def extract_allergens(message: str) -> list[str]:
    """Deterministically extract safety-critical allergens from a message.

    The LLM may also return allergens, but this function ensures phrases like
    "lunch no seafood" or "I am allergic to shellfish" are never missed just
    because a particular model omitted the field.
    """
    text = (message or "").lower()
    if not text:
        return []
    out: set[str] = set()

    # Direct per-term patterns (covers most phrasings).
    for term, groups in sorted(_USER_TERMS.items(), key=lambda kv: len(kv[0]), reverse=True):
        escaped = re.escape(term)
        patterns = [
            rf"\ballergic\s+to\s+{escaped}\b",
            rf"\b{escaped}\s+allergy\b",
            rf"\b{escaped}\s+intolerance\b",
            rf"\b{escaped}\s+intolerant\b",
            rf"\b(?:can't|cannot|can\s+not|don't|do\s+not)\s+eat\s+{escaped}\b",
            rf"\bavoid\s+{escaped}\b",
            rf"\bno\s+{escaped}\b",
            rf"\bwithout\s+{escaped}\b",
            rf"\bfree\s+(?:of|from)\s+{escaped}\b",
        ]
        # "nut-free"/"gluten-free" are dietary certifications, not allergens.
        # Other "-free" phrases (dairy-free, egg-free, peanut-free, ...) remain
        # allergen requests.
        if term not in DIETARY_FREE_TERMS:
            patterns.append(rf"\b{escaped}\s*-?\s*free\b")
        # Celiac/coeliac is a gluten allergy indicator even without the word
        # "allergy".
        if term in {"celiac", "coeliac"}:
            patterns.append(rf"\b{escaped}\b")
        if any(re.search(p, text) for p in patterns):
            out.update(groups)

    # Clause scan catches lists ("no seafood or shellfish", "allergic to X, Y").
    for trigger in _CLAUSE_TRIGGER.finditer(text):
        clause = text[trigger.end() : trigger.end() + 100]
        clause = re.split(r"[.;!?]", clause, maxsplit=1)[0]
        for term, groups in _USER_TERMS.items():
            if re.search(r"\b" + re.escape(term) + r"\b", clause):
                out.update(groups)

    return sorted(out)


def _restaurant_text(restaurant: dict) -> str:
    parts = [
        restaurant.get("name", ""),
        restaurant.get("cuisine", ""),
        " ".join(restaurant.get("cuisine_tags") or []),
        " ".join(restaurant.get("tags") or []),
        restaurant.get("description", ""),
    ]
    parts += [item.get("name", "") for item in (restaurant.get("menu") or [])]
    parts += [item.get("description", "") for item in (restaurant.get("menu") or [])]
    return " ".join(parts).lower()


def _inside_any_phrase(text: str, start: int, end: int, phrases: Iterable[str]) -> bool:
    for phrase in phrases:
        for m in re.finditer(re.escape(phrase), text, re.IGNORECASE):
            if m.start() <= start and m.end() >= end:
                return True
    return False


def _detect_from_text(text: str) -> set[str]:
    out: set[str] = set()
    for term, groups in sorted(_INGREDIENT_TERMS.items(), key=lambda kv: len(kv[0]), reverse=True):
        pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            start, end = match.start(), match.end()
            # Skip negated/absent mentions ("no seafood", "gluten-free").
            if _FREE_AFTER.match(text[end : end + 12]):
                continue
            if _NEGATION_BEFORE.search(text[max(0, start - 40) : start]):
                continue
            # Skip plant-based/non-dairy phrases for dairy terms.
            if "dairy" in groups and _inside_any_phrase(text, start, end, _DAIRY_EXCEPTIONS):
                continue
            # "Water chestnut" is not a tree nut.
            if "tree-nut" in groups and _inside_any_phrase(text, start, end, _TREE_NUT_EXCEPTIONS):
                continue
            out.update(groups)
    return out


def detect_allergens(restaurant: dict) -> set[str]:
    """Return the canonical allergens a venue is assumed to contain.

    Uses explicit `allergens` metadata plus conservative text detection over the
    name, cuisine/tags, description, and menu. Explicit flags are trusted; text
    detection catches ingredients that were not manually annotated.
    """
    explicit = set(normalize_allergens(restaurant.get("allergens") or []))
    return explicit | _detect_from_text(_restaurant_text(restaurant))
