# Test 1b — Dietary constraint (hard constraint compliance)

**Date:** 2026-10-25 · **Mode:** Demo (no LLM) · **Constraint tested:** every recommendation must be **vegan**

## Input
```
Vegan lunch near campus
```

## Expected Output
- `parsed →` badge: `meal: lunch · dietary: vegan` (demo keyword parser maps "vegan" → dietary)
- **Every** recommended restaurant must carry the `vegan` dietary tag
- Expected recommended restaurants (dataset, vegan + serves lunch):
  1. **Sun Kee Curry House** — Indian, ★4.7, ~55 HKD, 7 min walk
  2. **Café 88** — Western, ★4.4, ~95 HKD, 5 min walk
  3. **Jade Garden Vegetarian** — Vegetarian, ★4.4, ~78 HKD, 7 min walk
  4. **Green Bowl Salad Bar** — Healthy, ★4.2, ~70 HKD, 9 min walk
- Non-vegan places (Dim Sum Dynasty, Hana Sushi, Pokfulam Thai & Grill, Water Street Noodle House, Kennedy Town Grill House) must NOT appear

## Actual Output
**LLM direct response message (demo template summary):**
> Here are 4 spot(s) around HKU for lunch · vegetarian+vegan. Top pick: **Sun Kee Curry House** (Indian, ~55 HKD, 7 min walk, 4.7/5).

**Parsed badge:** `meal: lunch · dietary: vegetarian+vegan`

**List of recommended restaurants:**
1. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
   - 💡 "serves lunch; matches your keywords"
2. **Café 88** — $$ · ★4.4 · Western · 5 min walk · ~95 HKD
   - 💡 "serves lunch; matches your keywords; very close walk"
3. **Jade Garden Vegetarian** — $$ · ★4.4 · Vegetarian · 7 min walk · ~78 HKD
   - 💡 "serves lunch; matches your keywords"
4. **Green Bowl Salad Bar** — $$ · ★4.2 · Healthy · 9 min walk · ~70 HKD
   - 💡 "serves lunch; matches your keywords"

## Verdict
✅ **PASS** — All 4 picks carry the `vegan` tag in the dataset; no non-vegan restaurant was returned. (Note: the demo parser extracted `vegetarian+vegan`, which is a superset — still correct.)
