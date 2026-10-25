# Test 1a — Price constraint (hard constraint compliance)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** every recommendation must be price level `$` (cheap)

## Input
```
Cheap curry for dinner, student budget
```

## Expected Output
- `parsed →` badge: `meal: dinner · price: $`
- **Every** recommended restaurant must be price level `$` (single `$` on the card)
- Expected recommended restaurants (dataset, price 1):
  1. **Sun Kee Curry House** — Indian, ★4.7, ~55 HKD, 7 min walk (best curry match)
  2. **Sweet Corner Desserts** — Desserts, ★4.8, ~38 HKD, 2 min walk (cheap, but not curry)
- No `$$` or `$$$` restaurant may appear

## Actual Output
**LLM direct response message:**
> Sun Kee is the better match for a cheap curry dinner, while Sweet Corner is only a cheap dessert add-on.

**Parsed badge:** `meal: dinner · price: $`

**List of recommended restaurants:**
1. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
   - 💡 "It directly matches your curry and budget keywords with a 7-minute walk, though $55 is a modest student spend rather than ultra-cheap."
2. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD
   - 💡 "It is cheap and very close, but it is a dessert spot rather than a curry dinner, so only use it as an after-meal treat."

## Verdict
✅ **PASS** — Price constraint held for every pick (both `$`). Bonus: the LLM honestly flagged Sweet Corner as not a curry dinner rather than over-selling it.
