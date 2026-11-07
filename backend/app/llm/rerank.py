"""Constrained LLM re-ranking / selection (Phase 3).

The backend stays the authority on safety and hard constraints:

1. Candidate generation is deterministic (`search_ranked_pool`): hard filters ->
   strict soft preferences (or disclosed fallback) -> weighted + BM25 ranking.
2. Top-K candidates are offered to the LLM, which may only *choose and order*
   ids from that list and give a short reason per pick.
3. Every LLM pick is validated here: unknown ids, duplicates, non-candidate
   restaurants, and any hard-constraint/allergen violation are rejected. Missing
   slots are repaired from the deterministic ranking.
4. Any provider error, timeout, invalid JSON, or empty selection falls back to
   the deterministic order.

The LLM can therefore improve personalization but can never invent restaurants,
override allergens/meal/time/avoid, or bypass the backend's relaxation state.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field

from ..allergens import ALLERGEN_SHORT_LABELS
from ..config import (
    LLM_RERANK_ENABLED,
    LLM_RERANK_TIMEOUT_SECONDS,
)
from ..recommend import card, hard_constraint_violation
from ..schemas import ParseResult
from .providers import LLMError, get_provider

logger = logging.getLogger(__name__)

# Response `selection_mode` values.
SELECTION_LLM = "llm_rerank"
SELECTION_DETERMINISTIC = "deterministic"
SELECTION_FALLBACK = "fallback"

_FIELD_LABELS = {
    "price_level": "price",
    "dietary": "dietary",
    "allergens": "allergens",
    "cuisines": "cuisine",
    "preferences": "preference",
    "open_at": "opening time",
    "meal": "meal",
}


def rerank_schema(max_picks: int) -> dict:
    """Strict output schema: an ordered list of candidate ids + reasons."""
    return {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "description": (
                    "Ordered selection of AT MOST "
                    f"{max_picks} restaurant ids copied exactly from the candidate "
                    "list, best first. Use fewer if fewer genuinely fit."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Restaurant id from the candidate list only",
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "One concise sentence on why this candidate fits the "
                                "user's request, using only the provided facts."
                            ),
                        },
                    },
                    "required": ["id", "reason"],
                },
            },
            "summary": {
                "type": "string",
                "description": (
                    "One or two sentences summarizing the selection and any "
                    "trade-off (relaxed filter, unmet preference)."
                ),
            },
        },
        "required": ["picks", "summary"],
    }


def _menu_highlights(restaurant: dict, count: int = 4) -> list[str]:
    out: list[str] = []
    for item in (restaurant.get("menu") or [])[:count]:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        price = item.get("price")
        out.append(f"{name} ({price})" if price not in (None, "") else name)
    return out


def _hours(restaurant: dict) -> list[str]:
    out: list[str] = []
    for slot in restaurant.get("opening") or []:
        try:
            out.append(f"{slot['open']}-{slot['close']}")
        except (KeyError, TypeError):
            continue
    return out


def build_candidates(pool: list[dict]) -> list[dict]:
    """Build the fact sheet for each deterministically ranked candidate."""
    candidates: list[dict] = []
    for rank, item in enumerate(pool, start=1):
        r = item["restaurant"]
        c = card(r, "; ".join(item.get("reasons") or []))
        candidates.append(
            {
                "rank": rank,
                "id": r["id"],
                "name": r["name"],
                "cuisine": r["cuisine"],
                "cuisine_tags": r.get("cuisine_tags") or [],
                "price_level": r.get("price_level"),
                "price_symbol": c["price_symbol"],
                "avg_cost": r.get("avg_cost"),
                "rating": r.get("rating"),
                "area": r.get("area"),
                "walk_minutes": r.get("walk_minutes"),
                "tags": (r.get("tags") or [])[:6],
                "preference_tags": c["preference_tags"],
                "dietary": r.get("dietary") or [],
                "allergens": c["allergens"],
                "hours": _hours(r),
                "menu_highlights": _menu_highlights(r),
                "matched": item.get("reasons") or [],
                "soft_mismatches": item.get("soft_mismatches") or [],
            }
        )
    return candidates


def _format_candidates(candidates: list[dict]) -> str:
    lines: list[str] = []
    for c in candidates:
        lines.append(
            f"#{c['rank']} id={c['id']} | {c['name']} | {c['cuisine']}, {c['area']} | "
            f"{c['price_symbol']} (avg {c['avg_cost']} HKD) | ★{c['rating']}/5 | "
            f"{c['walk_minutes']} min walk"
        )
        facts = [
            "tags: " + ", ".join(c["tags"]) if c["tags"] else "",
            "preference tags: " + ", ".join(c["preference_tags"])
            if c["preference_tags"]
            else "",
            "dietary: " + ", ".join(c["dietary"]) if c["dietary"] else "",
            "detected allergens: " + ", ".join(c["allergens"]) if c["allergens"] else "",
            "hours: " + " / ".join(c["hours"]) if c["hours"] else "",
            "menu: " + "; ".join(c["menu_highlights"]) if c["menu_highlights"] else "",
            "backend match: " + "; ".join(c["matched"]) if c["matched"] else "",
            "unmet soft preference: " + "; ".join(c["soft_mismatches"])
            if c["soft_mismatches"]
            else "",
        ]
        lines.extend(f"   {fact}" for fact in facts if fact)
    return "\n".join(lines)


def _build_prompt(
    message: str,
    p: ParseResult,
    candidates: list[dict],
    limit: int,
    relaxed: list[str],
    soft_fallback: bool,
    unmet_soft: list[str],
) -> tuple[str, str]:
    allergen_labels = ", ".join(ALLERGEN_SHORT_LABELS.get(a, a) for a in p.allergens or [])
    lines: list[str] = []
    lines.append(
        "Choose and order the best restaurants for the user from the candidate "
        f"list below. Select AT MOST {limit} ids. Only ids that appear in the "
        "candidate list are allowed."
    )
    lines.append("")
    lines.append("<user_request>" + (message or "").strip() + "</user_request>")
    lines.append("<applied_filters>" + json.dumps(p.model_dump(), ensure_ascii=False) + "</applied_filters>")
    if allergen_labels:
        lines.append(
            "<safety>SAFETY: the user must avoid " + allergen_labels + ". The backend "
            "already removed matching venues; never pick a venue whose detected "
            "allergens overlap the list and never claim a venue is allergen-free.</safety>"
        )
    if relaxed:
        relaxed_labels = ", ".join(_FIELD_LABELS.get(f, f) for f in relaxed)
        lines.append(
            "<relaxation>The backend relaxed the following filter(s) to find these "
            f"candidates: {relaxed_labels}. Respect this relaxed state — do not "
            "re-apply the stricter original filter. Mention the trade-off in the "
            "summary.</relaxation>"
        )
    if soft_fallback:
        soft_labels = ", ".join(_FIELD_LABELS.get(f, f) for f in (unmet_soft or []))
        lines.append(
            "<soft_fallback>No candidate satisfies all soft preferences"
            + (f" ({soft_labels})" if soft_labels else "")
            + ". These are the closest options that satisfy the hard constraints. "
            "Be honest about which preference is unmet.</soft_fallback>"
        )
    lines.append(
        "<rules>"
        "1. Copy ids exactly from the candidate list; never invent restaurants or ids. "
        "2. Never pick a candidate whose facts contradict the user's meal, opening time, "
        "price/relaxation state, allergens, or 'avoid' list. "
        "3. Use only the facts listed for each candidate: no invented prices, ratings, "
        "hours, amenities or dishes. "
        "4. Order picks best-first for this specific request and keep each reason under "
        "40 words. "
        "5. Return JSON only, matching the schema; use an empty list if nothing fits."
        "</rules>"
    )
    lines.append(
        '<output_format>Return ONLY JSON with exactly this shape: {"picks": '
        '[{"id": "<id copied from the candidate list>", "reason": "<one sentence>"}], '
        '"summary": "<one or two sentences>"}. Use the key "picks" — do not rename it '
        '(not "recommendations", "results" or "selection").</output_format>'
    )
    lines.append("<schema>" + json.dumps(rerank_schema(limit)) + "</schema>")
    lines.append("")
    lines.append("<candidates>")
    lines.append(_format_candidates(candidates))
    lines.append("</candidates>")

    system = (
        "You are the selection layer of a restaurant recommender for HKU students. "
        "You may ONLY choose and order restaurant ids from the provided candidate "
        "list; the backend has already enforced meal, price, opening-time and "
        "allergen constraints. Never invent data and never override a safety "
        "constraint. Reply with ONLY a JSON object conforming exactly to the schema."
    )
    return system, "\n".join(lines)


@dataclass
class ValidationResult:
    """Outcome of validating the LLM's selection against backend rules."""

    ordered_ids: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    rejected: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.ordered_ids)


def validate_selection(
    data: dict | None,
    candidates: list[dict],
    p: ParseResult,
    limit: int,
    restaurants_by_id: dict[str, dict],
) -> ValidationResult:
    """Validate/reap an LLM selection; returns only safe, candidate-backed ids.

    Rejections (recorded in `rejected`): invalid shape, missing/duplicate ids,
    ids that are not candidates, and picks violating a hard constraint (allergens,
    meal, price/relaxation state, opening time, avoid).
    """
    result = ValidationResult()
    if not isinstance(data, dict):
        result.rejected.append({"id": None, "reason": "invalid_shape"})
        return result
    raw = data.get("picks")
    summary = data.get("summary")
    if isinstance(summary, str):
        result.summary = summary.strip()[:500]
    if not isinstance(raw, list):
        result.rejected.append({"id": None, "reason": "invalid_picks"})
        return result

    candidate_ids = {c["id"] for c in candidates}
    seen: set[str] = set()
    for item in raw:
        if len(result.ordered_ids) >= limit:
            break
        if not isinstance(item, dict):
            result.rejected.append({"id": None, "reason": "invalid_item"})
            continue
        rid = item.get("id")
        if not isinstance(rid, str) or not rid.strip():
            result.rejected.append({"id": None, "reason": "missing_id"})
            continue
        rid = rid.strip()
        if rid not in candidate_ids:
            result.rejected.append({"id": rid, "reason": "unknown_id"})
            continue
        if rid in seen:
            result.rejected.append({"id": rid, "reason": "duplicate"})
            continue
        seen.add(rid)
        restaurant = restaurants_by_id.get(rid)
        if restaurant is None:
            result.rejected.append({"id": rid, "reason": "unknown_id"})
            continue
        violation = hard_constraint_violation(restaurant, p)
        if violation:
            # The LLM may never override allergens/meal/time/price/avoid.
            result.rejected.append({"id": rid, "reason": f"unsafe:{violation}"})
            continue
        result.ordered_ids.append(rid)
        reason = item.get("reason")
        if isinstance(reason, str) and reason.strip():
            result.reasons[rid] = reason.strip()[:300]
    return result


@dataclass
class RerankCall:
    """Raw provider call result for a re-rank attempt."""

    ok: bool
    data: dict | None = None
    error: str = ""


def _call_with_timeout(
    config: dict,
    system: str,
    user: str,
    schema: dict,
    max_tokens: int,
    timeout: float,
) -> dict:
    """Call the provider with a hard wall-clock budget.

    A thread is used so a hanging provider can never stall the chat response;
    the HTTP layer is also bounded by the same timeout so the worker finishes
    shortly after we stop waiting for it.
    """
    provider = get_provider(config, timeout=timeout)
    if provider is None:
        raise LLMError("No LLM configured")
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(provider.chat_json, system, user, schema, max_tokens)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError as e:
        raise LLMError(f"LLM re-rank timed out after {timeout:g}s") from e
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def rerank(
    config: dict,
    message: str,
    p: ParseResult,
    candidates: list[dict],
    limit: int,
    *,
    relaxed: list[str] | None = None,
    soft_fallback: bool = False,
    unmet_soft: list[str] | None = None,
    timeout: float | None = None,
) -> RerankCall:
    """Ask the LLM to select/reorder candidates; never raises."""
    if not candidates:
        return RerankCall(ok=False, error="no candidates")
    budget = float(timeout or LLM_RERANK_TIMEOUT_SECONDS)
    system, user = _build_prompt(
        message,
        p,
        candidates,
        limit,
        list(relaxed or []),
        soft_fallback,
        list(unmet_soft or []),
    )
    try:
        data = _call_with_timeout(
            config, system, user, rerank_schema(limit), 900, budget
        )
    except Exception as e:  # noqa: BLE001 - any provider/parse failure -> fallback
        logger.warning("LLM re-rank failed, using deterministic order: %s", e)
        return RerankCall(ok=False, error=str(e))
    if not isinstance(data, dict):
        logger.warning("LLM re-rank returned non-object JSON; using deterministic order")
        return RerankCall(ok=False, error="non-object JSON")
    return RerankCall(ok=True, data=data)


@dataclass
class SelectionOutcome:
    """Final ordered picks + selection metadata for the chat response."""

    picks: list[dict]
    selection_mode: str
    candidate_count: int
    reasons: dict[str, str] = field(default_factory=dict)
    summary: str = ""
    error: str = ""


def select_picks(
    pool: list[dict],
    p: ParseResult,
    limit: int,
    config: dict,
    message: str,
    *,
    relaxed: list[str] | None = None,
    soft_fallback: bool = False,
    unmet_soft: list[str] | None = None,
    enabled: bool = True,
    timeout: float | None = None,
) -> SelectionOutcome:
    """Select final picks: constrained LLM re-rank when possible, else deterministic.

    `pool` is the deterministically ordered candidate set (top-K). The returned
    picks are always a subset/permutation of that pool: the LLM cannot introduce
    a restaurant the backend did not generate.
    """
    deterministic = pool[: max(0, limit)]
    candidates = build_candidates(pool)
    candidate_count = len(candidates)

    if not pool or not deterministic:
        return SelectionOutcome([], SELECTION_DETERMINISTIC, 0)

    if not enabled or limit <= 0:
        return SelectionOutcome(deterministic, SELECTION_DETERMINISTIC, candidate_count)

    call = rerank(
        config,
        message,
        p,
        candidates,
        limit,
        relaxed=relaxed,
        soft_fallback=soft_fallback,
        unmet_soft=unmet_soft,
        timeout=timeout,
    )
    if not call.ok:
        return SelectionOutcome(
            deterministic, SELECTION_FALLBACK, candidate_count, error=call.error
        )

    restaurants_by_id = {item["restaurant"]["id"]: item["restaurant"] for item in pool}
    validation = validate_selection(
        call.data, candidates, p, limit, restaurants_by_id
    )
    if not validation.ok:
        logger.warning(
            "LLM re-rank produced no valid picks (rejected=%s); using deterministic order",
            validation.rejected,
        )
        return SelectionOutcome(
            deterministic,
            SELECTION_FALLBACK,
            candidate_count,
            error="empty or invalid selection",
        )

    by_id = {item["restaurant"]["id"]: item for item in pool}
    chosen: list[dict] = []
    chosen_ids: set[str] = set()
    for rid in validation.ordered_ids:
        chosen.append(by_id[rid])
        chosen_ids.add(rid)
    # Repair missing slots from the deterministic ranking (never duplicates).
    for item in pool:
        if len(chosen) >= limit:
            break
        rid = item["restaurant"]["id"]
        if rid in chosen_ids:
            continue
        chosen.append(item)
        chosen_ids.add(rid)

    return SelectionOutcome(
        chosen,
        SELECTION_LLM,
        candidate_count,
        reasons=validation.reasons,
        summary=validation.summary,
    )


__all__ = [
    "SELECTION_LLM",
    "SELECTION_DETERMINISTIC",
    "SELECTION_FALLBACK",
    "LLM_RERANK_ENABLED",
    "build_candidates",
    "rerank_schema",
    "validate_selection",
    "rerank",
    "select_picks",
    "ValidationResult",
    "RerankCall",
    "SelectionOutcome",
]
