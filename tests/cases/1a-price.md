# Test 1a — Price constraint (hard constraint compliance)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** every recommendation must be price level `$` (cheap)

## Input
```
Cheap curry for dinner, student budget
```

## Expected Output
- `parsed →` badge: `meal: dinner · price: $` (cuisine `Indian` is a soft preference).
- **Every** recommended restaurant must be price level `$` (single `$` on the card).
- Expected recommended restaurant:
  1. **Sun Kee Curry House** — Indian, ★4.7, ~55 HKD, 7 min walk (best curry match)
- **Sweet Corner Desserts is excluded** while an Indian/curry match exists, because
  cuisine is a soft preference and Sweet Corner does not match it.
- No `$$` or `$$$` restaurant may appear.

## Actual Output — before soft-preference refinement
**LLM direct response message:**
> Sun Kee is the better match for a cheap curry dinner, while Sweet Corner is only a cheap dessert add-on.

**Parsed badge:** `meal: dinner · price: $`

**List of recommended restaurants:**
1. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
2. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD

## Post-refinement behavior
- Only **Sun Kee Curry House** is returned when an Indian/curry match exists.
- If no cheap curry/Indian venue existed, the backend would fall back to
  hard-constraint matches (including Sweet Corner) and explicitly say that no
  restaurant matched all preferences (`soft_fallback: true`).

## Verdict
✅ **PASS** — Price constraint holds for every pick. With soft-preference gating,
the non-curry Sweet Corner is no longer mixed into a curry request when a curry
match exists.
