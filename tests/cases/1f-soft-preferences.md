# Test 1f — Soft preferences (strict first, disclosed fallback)

**Date:** 2026-10-31 · **Mode:** Demo + LLM · **Scope:** dietary and cuisine are soft preferences; hard constraints remain strict.

## Rules
- **Hard constraints:** meal, price, opening time, allergens, avoided features.
- **Full-meal rule:** breakfast/lunch/dinner requests exclude dessert/snack venues, even if they list that meal or are open at that time. Snack/dessert requests still allow them.
- **Soft preferences:** dietary labels, cuisine.
- **Strict first:** if at least one restaurant satisfies every hard constraint and every soft preference, only those restaurants are returned.
- **Fallback:** if none do, hard-constraint matches are returned with `soft_fallback: true`, `unmet_soft` listing the soft fields, per-card `soft_mismatches`, and an explicit summary sentence: “No restaurant matches all your preferences (…); I’m showing the closest options that satisfy your hard constraints.”

## Case A — Cuisine strict match
**Input:** `Cheap curry for dinner, student budget`

Expected:
- Parsed badge: `meal: dinner · price: $ · cuisines: Indian` (deterministic enrichment adds Indian from “curry” even if the LLM omits it).
- Only **Sun Kee Curry House**.
- Sweet Corner Desserts is excluded (cuisine mismatch + dessert venue for a full meal).
- `status: ok`, `soft_fallback: false`.

## Case B — Cuisine fallback
**Input:** `Cheap noodle lunch`

Expected:
- No cheap noodle venue exists.
- Fallback card: **Sun Kee Curry House** only (`$`, full lunch).
- Sweet Corner Desserts is excluded because it is a dessert/snack venue.
- `status: soft_fallback`, `unmet_soft: ["cuisines"]`.
- Card shows `⚠️ Partial match: cuisine: Noodles`.
- Summary explicitly says: **“No restaurant matches all your preferences (cuisine); I’m showing the closest options that satisfy your hard constraints.”**

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
