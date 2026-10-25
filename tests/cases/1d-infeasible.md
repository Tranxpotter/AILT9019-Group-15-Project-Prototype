# Test 1d — Infeasible combination (must refuse honestly)

**Date:** 2026-10-25 · **Mode:** Demo (no LLM) · **Constraint tested:** no restaurant satisfies *all three* (price `$` + vegan + breakfast) → system must tell the user it cannot find a suitable one

## Input
```
Cheap vegan breakfast
```

## Expected Output
- **No recommendation cards** (no restaurant in the dataset is price-1 + vegan + serves breakfast)
- Expected message: an explicit "I could not find a restaurant that fits all your constraints. Try relaxing the price, meal or time filters." style refusal
- The user must be told that **no suitable restaurant exists**

## Actual Output
**LLM direct response message (demo template summary):**
> Here are 2 spot(s) around HKU for breakfast · vegan. Top pick: **Café 88** (Western, ~95 HKD, 5 min walk, 4.4/5). (I relaxed the price_level filter(s) to find these.)

**Parsed badge:** `meal: breakfast · price: $ · dietary: vegan`

**List of recommended restaurants:**
1. **Café 88** — **$$** · ★4.4 · Western · 5 min walk · ~95 HKD
   - 💡 "serves breakfast; matches your keywords; very close walk"
2. **Green Bowl Salad Bar** — **$$** · ★4.2 · Healthy · 9 min walk · ~70 HKD
   - 💡 "serves breakfast; matches your keywords"

## Verdict
⚠️ **KNOWN LIMITATION (expected to fail)** — The system did **not** say "no suitable restaurant found". Instead it silently relaxed the price constraint and returned two `$$` (not `$`) restaurants.
- Demo mode *did* disclose the relaxation: "(I relaxed the price_level filter(s) to find these.)" ✅
- But the "could not find a suitable one" branch is effectively **unreachable** with this dataset (dropping all filters always yields matches), so the user is never given a true refusal.
- In **LLM mode** the relaxation would **not** be disclosed at all (the `relaxed` list is not passed to `explain_llm()`), so the AI would present `$$` picks as satisfying "cheap" — inconsistent honesty between the two output paths.
- **Planned fix:** hard-constraint mode → explicit "no suitable restaurant" response when the filtered set is empty; or always disclose relaxation in both modes.
