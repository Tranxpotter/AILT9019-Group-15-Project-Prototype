# Test 3a — Factual accuracy / no hallucination (rating & price)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** every factual claim (rating, price, distance, cuisine) must match the dataset; no invented amenities

## Input
```
Recommend a budget Indian curry place for dinner and tell me why it's good
```

## Expected Output
- Top pick: **Sun Kee Curry House**
- **Ground truth (from `backend/data/restaurants.json`):**
  - Rating **4.7** · Avg **$55** · Cuisine **Indian** · **7 min walk**
  - Hours **11:30–22:30** · Dietary: vegetarian, vegan, halal, gluten-free · Price level `$`
- **Must NOT contain (hallucination check):** "4.9"/"5.0" (wrong rating), "$20" (wrong price), invented amenities such as "rooftop", "live music", "free wifi", "24 hours", "open all night"

## Actual Output
**LLM direct response message:**
> Sun Kee Curry House is the best match for a budget Indian curry dinner, while Sweet Corner is only a cheap dessert option if you want a sweet finish.

**Parsed badge:** `meal: dinner · cuisines: Indian · price: $`

**List of recommended restaurants:**
1. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
   - 💡 "It directly matches your Indian curry dinner request with a budget-friendly $55 average, strong 4.7 rating, and a 7-minute walk, though it is slightly farther than the dessert spot."
2. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD
   - 💡 "It is not an Indian curry place, but it suits a cheap late-night dessert add-on at $38 and 2 minutes away if you want something sweet after dinner."

## Verdict
✅ **PASS — no hallucination detected.**
- All factual values in the AI text match the dataset: **$55** avg, **4.7** rating, **7-minute** walk, **Indian** cuisine. ✅
- No invented amenities (no "rooftop / live music / free wifi / 24 hours"). ✅
- Bonus: the AI correctly labeled Sweet Corner as *not* an Indian curry place rather than forcing a false match.
