# Test 1f — Soft preferences: food-type intent outranks price

**Date:** 2026-10-31 · **Mode:** Demo + LLM · **Scope:** dietary/cuisine/preferences are soft; food-type intent outranks the price band.

## Rules
- **Hard constraints:** meal, price, opening time, allergens, avoided features.
- **Full-meal rule:** breakfast/lunch/dinner requests exclude dessert/snack venues, even if they list that meal or are open at that time. Snack/dessert requests still allow them.
- **Soft preferences:** dietary labels, cuisine, dish_intent/texture/vibe.
- **Strict first:** if at least one restaurant satisfies every hard constraint and every soft preference, only those restaurants are returned.
- **Food-type over price:** if a cuisine/dish/texture/vibe match exists only outside the price band, relax **only price**, return the food-type match, and disclose the relaxation (`relaxed: ["price_level"]`).
- **Fallback:** if no food-type match exists at any price, hard-constraint matches are returned with `soft_fallback: true`, `unmet_soft`, per-card `soft_mismatches`, and an explicit summary sentence.

## Case A — Cuisine strict match
**Input:** `Cheap curry for dinner, student budget`

Expected:
- Parsed badge: `meal: dinner · price: $ · cuisines: Indian` (deterministic enrichment adds Indian from “curry” even if the LLM omits it).
- Only **Sun Kee Curry House**.
- Sweet Corner Desserts is excluded (cuisine mismatch + dessert venue for a full meal).
- `status: ok`, `soft_fallback: false`.

## Case B — Food-type over price
**Input:** `Cheap noodle lunch`

Expected:
- No **cheap** noodle venue exists, but food-type intent outranks price.
- Only **Water Street Noodle House** (`$$`, Noodles, lunch).
- Sweet Corner Desserts is excluded as a dessert venue.
- `status: relaxed`, `relaxed: ["price_level"]`, `soft_fallback: false`, `unmet_soft: []`.
- Summary includes: **“Note: no restaurant matched all filters, so I relaxed the price filter(s) — these picks may not meet that constraint.”**
- No `⚠️ Partial match` note on the card.

## Case B2 — More food-type-over-price cases
| Input | Expected |
|---|---|
| `Cheap sushi lunch` | **Hana Sushi** (`$$$`), price relaxed |
| `Cheap Thai lunch` | **Pokfulam Thai & Grill** (`$$`), price relaxed |
| `Cheap grilled lunch` | **Pokfulam Thai & Grill** (`$$`), price relaxed |
| `Cheap healthy lunch` | **Green Bowl Salad Bar** + **Jade Garden Vegetarian** (`$$`), price relaxed |
| `Cheap noodle breakfast` | **Water Street Noodle House** (`$$`), price relaxed |
| `Cheap vegan breakfast` | **No suitable restaurant found** (no food-type intent; hard refusal preserved) |

## Case C — Dietary fallback
**Input:** `Cheap vegan snack`

Expected:
- Hard matches: Sweet Corner Desserts (`$`, snack).
- Sweet Corner is vegetarian but not vegan.
- `status: soft_fallback`, `unmet_soft: ["dietary"]`.
- Card shows `⚠️ Partial match: dietary: vegan`.
- Summary explicitly says no restaurant matches all preferences (dietary).

## Case D — Dietary strict match
**Input:** `Vegan lunch near campus`

Expected:
- Only vegan lunch venues: **Café 88, Sun Kee Curry House, Green Bowl Salad Bar, Jade Garden Vegetarian**.
- `status: ok`, `soft_fallback: false`.

## Case E — Vegetarian is dietary, not a duplicate cuisine
**Input:** `Vegetarian lunch`

Expected:
- Parsed badge shows `dietary: vegetarian`, **no** `cuisines: Vegetarian`.
- Returns all full-lunch venues with the vegetarian dietary label: Café 88, Sun Kee Curry House, Dim Sum Dynasty, Green Bowl Salad Bar, Jade Garden Vegetarian. Sweet Corner Desserts is excluded as a dessert venue.
- `status: ok`.

## Case F — Dessert strict match
**Input:** `cheap dessert`

Expected:
- Only **Sweet Corner Desserts**.
- Sun Kee Curry House must **NOT** appear, even if the LLM leaves `meal` unset, because cuisine `Desserts` is a strict soft preference when a dessert match exists.
- `status: ok`.

## Verdict
✅ **Behavior implemented** — soft preferences no longer flood the result list; fallback is explicit and disclosed in both Demo and LLM modes. Full-meal requests exclude dessert/snack venues; snack/dessert requests still allow them.
