# Test 3b — Factual accuracy / no hallucination (schedule & description)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** description, rating, price, and any schedule claims must match the dataset; no invented hours/features

## Input
```
Best sushi spot near campus
```

## Expected Output
- Top pick: **Hana Sushi**
- **Ground truth (from `backend/data/restaurants.json`):**
  - Rating **4.5** · Avg **$165** · Cuisine **Japanese** · **12 min walk** · Price level `$$$`
  - Hours: **Tue–Sun 12:00–15:00 & 18:00–22:00** (closed Mondays)
  - Tags: sushi, **omakase**, lunch set, date night
- **Must NOT contain (hallucination check):** "open on Monday", "24 hours", "open all night", wrong hours, invented features (e.g. "sake bar", "live sushi counter" if absent from data)

## Actual Output
**LLM direct response message:**
> Hana Sushi is the best match for a sushi spot near campus, while the others are close but not Japanese.

**Parsed badge:** `cuisines: Japanese`

**List of recommended restaurants:**
1. **Hana Sushi** — $$$ · ★4.5 · Japanese · 12 min walk · ~165 HKD
   - 💡 "Hana Sushi is the only Japanese sushi pick near campus, with a solid 4.5 rating and omakase, though it's pricier and a 12-minute walk."
2. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD
   - 💡 "Sweet Corner Desserts is close and cheap, but it's dessert-focused, so it doesn't fit a best-sushi request."
3. **Water Street Noodle House** — $$ · ★4.6 · Noodles · 3 min walk · ~68 HKD
   - 💡 "Water Street Noodle House is nearby and affordable, but it's noodle-focused, not Japanese sushi, so it misses the request."
4. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
   - 💡 "Sun Kee Curry House is budget-friendly and highly rated, but it's Indian curry rather than sushi, so it's not a match."
5. **Café 88** — $$ · ★4.4 · Western · 5 min walk · ~95 HKD
   - 💡 "Café 88 is student-friendly and close, but it's Western brunch/coffee, not sushi, so it doesn't meet the request."

## Verdict
✅ **PASS — no hallucination detected.**
- All factual values match the dataset: **4.5** rating, **$165** avg, **12-minute** walk, **Japanese** cuisine. ✅
- "omakase" is a **real tag** on Hana Sushi in the dataset (verified in `restaurants.json`), so it is a grounded claim, not an invention. ✅
- No wrong schedule claims (no "open on Monday", no "24 hours"). ✅
- Bonus: for the 4 non-Japanese picks, the AI explicitly stated *why each one misses the request* ("not Japanese sushi", "not a match") — honest non-matches instead of forced selling.
