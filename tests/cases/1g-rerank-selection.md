# Test 1g — Constrained LLM re-ranking / selection (Phase 3)

**Date:** 2026-11-07 · **Mode:** LLM + Demo · **Scope:** the LLM may select/reorder final picks only from backend-generated candidates; the backend validates every pick and the deterministic order remains the fallback.

## Rules
- **Trigger:** an LLM is configured (provider + model), the feature flag is on, the request did not set `"rerank": false`, and ranking produced candidates. The parse step is **not** a gate: if parsing falls back to the keyword parser, the selector still runs. Only a backend with no LLM configured is always deterministic.
- The backend builds the candidate set deterministically (hard filters → strict soft preferences → weighted/BM25 ranking) and offers the top-K (`LLM_RERANK_POOL`, default 15).
- The LLM may only return ids copied from that candidate list, with a short reason each: `{picks: [{id, reason}], summary}`.
- Every pick is re-validated against allergens, meal, price/relaxation state, opening time, and `avoid`. Unknown/duplicate ids are rejected; missing slots are filled from the deterministic ranking.
- Provider error, timeout, invalid JSON, or empty selection ⇒ deterministic order (`selection_mode: "fallback"`, with `selection_note` explaining the cause; UI shows a subtle `↩︎ Deterministic ranking` badge).
- No LLM configured (Demo mode) ⇒ always deterministic (`selection_mode: "deterministic"`).

## Case A — Nuanced request gets re-ranked (LLM mode)
**Input:** `Something comforting and soupy for a date night`

Expected:
- A `🎯 LLM re-ranked N candidates` badge above the summary.
- Cards are ordered per the LLM's choice, and each `💡 reason` is the selector's one-sentence justification.
- Every card is a real restaurant from the dataset; no invented venue/attribute.
- API response: `"selection_mode": "llm_rerank"`, `"candidate_count": N` (> 0), `"selection_note": ""`.

## Case B — No LLM configured stays deterministic
**Input:** same request in Demo mode (provider = `No LLM (demo mode)`).

Expected:
- No selection badge.
- Cards follow the deterministic ranking.
- API response: `"selection_mode": "deterministic"`.

## Case C — Safety cannot be overridden
**Input:** `Lunch, no seafood` (LLM mode).

Expected:
- Water Street Noodle House, Pokfulam Thai & Grill, Dim Sum Dynasty, Hana Sushi, Jade Garden Vegetarian and Sweet Corner Desserts must NOT appear even if the selector suggests them; unsafe ids are rejected.
- Summary still contains “For safety, I excluded restaurants containing …”.
- If every LLM pick is rejected, the deterministic (all-safe) order is shown with `selection_mode: "fallback"`.

## Case D — Honest refusal preserved
**Input:** `Cheap vegan breakfast` (LLM mode).

Expected:
- `🚫 No suitable restaurant found` badge, empty picks.
- The selector is **never** called for an empty candidate set.
- API response: `"selection_mode": "deterministic"`, `"candidate_count": 0`.

## Case E — Price relaxation respected
**Input:** `Cheap noodle lunch` (LLM mode).

Expected:
- `status: relaxed`, `relaxed: ["price_level"]`; the selector does not re-apply the strict price band.
- Only Water Street Noodle House; summary discloses the price relaxation.
- API response: `"selection_mode": "llm_rerank"` or `"fallback"` (both keep the relaxed pick).

## Case F — API-only fallback check
```bash
# force deterministic selection for one request
curl -s -X POST http://127.0.0.1:8010/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Vegan lunch near campus","limit":5,"rerank":false}' \
  | jq '{selection_mode,candidate_count,picks:[.picks[].id]}'
# → {"selection_mode":"deterministic","candidate_count":4,"picks":[...]}
```

## Verdict
✅ **Behavior implemented** — selection metadata (`selection_mode`, `candidate_count`) is returned by `/api/chat`; validation and deterministic fallback keep M1 refusal, allergen safety, soft fallback and price-relaxation behavior intact. Automated coverage: `backend/scripts/test_rerank.py` plus the existing regression suites.
