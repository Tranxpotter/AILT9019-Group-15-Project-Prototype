# Test 1d — Infeasible combination (must refuse honestly)

**Date:** 2026-10-25 · **Mode:** Demo + LLM (both paths) · **Constraint tested:** no restaurant satisfies *all three* (price `$` + vegan + breakfast) → system must tell the user it cannot find a suitable one

## Input
```
Cheap vegan breakfast
```

## Expected Output
- **No recommendation cards** (no restaurant in the dataset is price-1 + vegan + serves breakfast)
- Expected message: an explicit "No suitable restaurant found. None of the restaurants around HKU match all of your constraints…" refusal
- The user must be told that **no suitable restaurant exists**

## Actual Output — before M1 fix (2026-10-25)
**Demo template summary:**
> Here are 2 spot(s) around HKU for breakfast · vegan. Top pick: **Café 88** (Western, ~95 HKD, 5 min walk, 4.4/5). (I relaxed the price_level filter(s) to find these.)

**Parsed badge:** `meal: breakfast · price: $ · dietary: vegan`

**List of recommended restaurants:**
1. **Café 88** — **$$** · ★4.4 · Western · 5 min walk · ~95 HKD
2. **Green Bowl Salad Bar** — **$$** · ★4.2 · Healthy · 9 min walk · ~70 HKD

## Post-fix behavior (M1, pending manual re-run)
Default request (`{"message": "Cheap vegan breakfast"}`) now returns:

- `status`: `no_match`
- `picks`: `[]` (no cards)
- `relaxed`: `[]`
- **Summary:**
  > No suitable restaurant found. None of the restaurants around HKU match all of your constraints (meal=breakfast, price=$, dietary=vegetarian+vegan). I did not relax any filters automatically. Try relaxing one of the constraints yourself — for example raise the price level, drop a dietary requirement, or choose a different meal — and ask again.

The UI shows a `🚫 No suitable restaurant found` badge above the summary and the
recommendation list shows "No matches".

Opt-in relaxation (`"relax": true`) still works, but now discloses the change:

- `status`: `relaxed`, `relaxed`: `["price_level"]`
- Summary ends with: *"Note: no restaurant matched all filters, so I relaxed the price filter(s) — these picks may not meet that constraint."*

## Verdict
🛠️ **FIX APPLIED (M1)** — strict ranking by default; explicit refusal when the filtered set is empty; relaxation only on explicit request and always disclosed in both Demo and LLM modes. Awaiting manual re-run to confirm.
