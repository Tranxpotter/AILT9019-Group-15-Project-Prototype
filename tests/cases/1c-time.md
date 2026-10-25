# Test 1c — Time constraint (hard constraint compliance)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** every recommendation must be **open at 22:30** (incl. midnight-crossing hours)

## Input
```
Dinner at 22:30, anywhere
```

## Expected Output
- `parsed →` badge: `meal: dinner · open at 22:30`
- **Every** recommended restaurant must be open at 22:30
- Expected recommended restaurants (dataset, open at 22:30, serve dinner):
  1. **Sweet Corner Desserts** — closes **01:00** (crosses midnight)
  2. **Sun Kee Curry House** — closes **22:30**
  3. **Pokfulam Thai & Grill** — closes **23:00**
  4. **Kennedy Town Grill House** — closes **23:30**
- **Hana Sushi must NOT appear** (dinner closes at 22:00 — 30 min too early)

## Actual Output
**LLM direct response message:**
> For a late 22:30 dinner with no other preferences, these options range from cheap and close to pricier and farther, so choose based on budget and how much you want to walk.

**Parsed badge:** `meal: dinner · open at 22:30`

**List of recommended restaurants:**
1. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD
   - 💡 "It's the cheapest and closest late-night option, though it's dessert-focused rather than a full dinner."
2. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD
   - 💡 "It's a budget, close late-night dinner with strong ratings, but you'll need to walk a bit farther than Sweet Corner."
3. **Pokfulam Thai & Grill** — $$ · ★4.3 · Thai · 4 min walk · ~110 HKD
   - 💡 "It's a close, group-friendly late dinner if you want Thai grill, but it costs more than the Sai Ying Pun budget options."
4. **Kennedy Town Grill House** — $$$ · ★4.1 · Burgers · 15 min walk · ~190 HKD
   - 💡 "It's the most upscale and scenic late-night choice, but it's the priciest and farthest walk."

## Verdict
✅ **PASS** — All 4 picks are open at 22:30 (closing times 22:30 / 23:00 / 23:30 / 01:00); the midnight-crossing window (Sweet Corner, 12:00–01:00) was handled correctly; **Hana Sushi (closes 22:00) was correctly excluded**.
