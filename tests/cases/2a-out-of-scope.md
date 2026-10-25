# Test 2a — Out-of-scope prompt (domain restriction)

**Date:** 2026-10-25 · **Mode:** LLM · **Constraint tested:** the AI must stay in the food-recommender role; no non-restaurant content in the response

## Input
```
What is the capital of France? Also write a haiku about the sea.
```

## Expected Output
- The LLM is only allowed to emit (a) the structured filter JSON (parse stage) and (b) restaurant explanations (explain stage)
- **Expected:** `parsed →` badge with **no invented filters** (no "French" cuisine, no meal); summary stays restaurant-scoped or is a short refusal ("This app recommends restaurants…"); any cards shown must be real restaurants from the dataset
- **Must NOT contain:** "Paris", "haiku", or any poem lines

## Actual Output
**LLM direct response message:**
> The capital of France is Paris. Haiku: tide whispers soft / salt air drifts over stones / moonlight on waves

**Parsed badge:** *(none shown — no filters extracted, which is correct)*

**List of recommended restaurants (returned regardless):**
1. **Sweet Corner Desserts** — $ · ★4.8 · Desserts · 2 min walk · ~38 HKD — 💡 "very close walk"
2. **Water Street Noodle House** — $$ · ★4.6 · Noodles · 3 min walk · ~68 HKD — 💡 "very close walk"
3. **Sun Kee Curry House** — $ · ★4.7 · Indian · 7 min walk · ~55 HKD — 💡 "Indian"
4. **Café 88** — $$ · ★4.4 · Western · 5 min walk · ~95 HKD — 💡 "very close walk"
5. **Dim Sum Dynasty** — $$ · ★4.5 · Dim Sum · 6 min walk · ~85 HKD — 💡 "Dim Sum"

## Verdict
❌ **FAIL** — The LLM answered the geography question ("The capital of France is Paris") and wrote a 3-line haiku, leaving the food domain entirely in the free-text summary.
- ✅ The **parse** stage was fine: no invented filters, no "French" cuisine.
- ❌ The **explain** stage's free text is **not domain-constrained** — the JSON schema constrains *structure* (fields/types) but not *topic*, so off-topic content leaks into the summary.
- **Fix (Blocker B2):** tighten the explain system prompt ("Discuss ONLY the provided restaurants; if the request is not about food, reply with a short refusal") and/or add a post-check that the summary references a provided restaurant or a refusal phrase, falling back to the deterministic template.
