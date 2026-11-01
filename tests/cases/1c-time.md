# Test 1c — Time constraint (hard constraint compliance)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** every recommendation must be **open at 22:30** (incl. midnight-crossing hours) and must be a **full-meal venue**

## Input
```
Dinner at 22:30, anywhere
```

## Expected Output
- `parsed →` badge: `meal: dinner · open at 22:30`
- **Every** recommended restaurant must be open at 22:30.
- Expected recommended restaurants (full-meal venues open at 22:30):
  1. **Sun Kee Curry House** — closes **22:30**
  2. **Pokfulam Thai & Grill** — closes **23:00**
  3. **Kennedy Town Grill House** — closes **23:30**
- **Hana Sushi must NOT appear** (dinner closes at 22:00 — 30 min too early).
- **Sweet Corner Desserts must NOT appear** — dessert/snack venues are excluded for full meals, even though it is open until 01:00.

## Actual Output — before full-meal exclusion
**LLM direct response message:**
> For a late 22:30 dinner with no other preferences, these options range from cheap and close to pricier and farther, so choose based on budget and how much you want to walk.

**Parsed badge:** `meal: dinner · open at 22:30`

**List of recommended restaurants:**
1. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD
2. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
3. **Pokfulam Thai & Grill** — $$ · ★4.3 · Thai · 4 min walk · ~110 HKD
4. **Kennedy Town Grill House** — $$$ · ★4.1 · Burgers · 15 min walk · ~190 HKD

## Post-refinement behavior
- **Sweet Corner Desserts is excluded** because it is a dessert venue and the request is for a full dinner.
- Cards: **Sun Kee Curry House, Pokfulam Thai & Grill, Kennedy Town Grill House**.
- Hana Sushi remains excluded (closes 22:00).
- The midnight-crossing time logic still applies to other venues.

## Verdict
✅ **PASS** — All returned picks are open at 22:30 and are full-meal venues; Hana Sushi (closes 22:00) and Sweet Corner (dessert-only) are correctly excluded.
