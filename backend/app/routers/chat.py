"""Chat endpoint: parse -> candidate generation -> optional LLM re-rank -> explain."""
from fastapi import APIRouter

from .. import db
from ..allergens import allergens_from_terms, normalize_allergens
from ..config import LLM_RERANK_ENABLED, LLM_RERANK_POOL
from ..llm.explain import (
    allergen_disclosure,
    demo_summary,
    explain_llm,
    no_match_summary,
    relaxation_disclosure,
    soft_fallback_disclosure,
)
from ..llm.parse import parse_message
from ..llm.providers import PROVIDER_INFO, get_provider
from ..llm.rerank import (
    SELECTION_DETERMINISTIC,
    SELECTION_FALLBACK,
    SelectionOutcome,
    select_picks,
)
from ..recommend import (
    card,
    filter_and_score,
    search_ranked_pool,
    split_soft_matches,
)
from ..schemas import ChatRequest, ChatResponse, ParseResult

router = APIRouter(prefix="/api", tags=["chat"])


def _merge(ui: ParseResult | None, parsed: ParseResult) -> ParseResult:
    """UI-selected filters take precedence over message-parsed ones.

    Allergens are always normalized and unioned: an allergy must never be
    dropped because one source (UI or LLM) omitted it. Allergen-like entries
    from `avoid` are promoted to allergens as well.
    """
    base = ui or ParseResult()
    allergens = normalize_allergens(
        list(base.allergens)
        + list(parsed.allergens)
        + allergens_from_terms(list(base.avoid) + list(parsed.avoid))
    )
    dietary = base.dietary or parsed.dietary
    cuisines = base.cuisines or parsed.cuisines
    # "Vegetarian" is a dataset cuisine label but is really a dietary preference.
    # When dietary already captures it, avoid double-constraining.
    if {"vegetarian", "vegan"} & set(dietary):
        cuisines = [c for c in cuisines if c.lower() != "vegetarian"]
    dish_intent = list(
        dict.fromkeys(list(base.dish_intent) + list(parsed.dish_intent))
    )
    texture = list(dict.fromkeys(list(base.texture) + list(parsed.texture)))
    vibe = list(dict.fromkeys(list(base.vibe) + list(parsed.vibe)))
    return ParseResult(
        meal=base.meal or parsed.meal,
        cuisines=cuisines,
        dish_intent=dish_intent,
        texture=texture,
        vibe=vibe,
        price_level=base.price_level or parsed.price_level,
        open_at=base.open_at or parsed.open_at,
        dietary=dietary,
        allergens=allergens,
        keywords=parsed.keywords or [],
        avoid=list(dict.fromkeys(base.avoid + parsed.avoid)),
        notes=parsed.notes,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    config = db.get_llm_config()
    parsed, mode = parse_message(config, req.message)
    merged = _merge(req.filters, parsed)

    restaurants = db.list_restaurants()
    # Candidate set offered to the constrained re-ranker: top-K, never fewer
    # than what the response needs.
    pool_limit = max(req.limit, min(LLM_RERANK_POOL, 50))

    def search(pr):
        scored = filter_and_score(restaurants, pr)
        selected, meta = split_soft_matches(scored, pr)
        return selected[:pool_limit], meta

    # Food-type intent outranks price: if a cuisine/dish/texture/vibe match only
    # exists outside the requested price band, relax only price and disclose it.
    pool, soft_meta, effective, auto_relaxed = search_ranked_pool(
        restaurants, merged, pool_limit
    )
    relaxed: list[str] = list(auto_relaxed)
    attempted: list[str] = []
    soft_fallback = soft_meta["soft_fallback"]
    unmet_soft = soft_meta["unmet_soft"]

    # Explicit opt-in relaxation (user asked for it via `relax: true`)
    if not pool and req.relax:
        # Opt-in relaxation: drop one non-safety hard filter at a time.
        # Allergens and dietary requirements are never relaxed.
        relaxed_candidates = [
            ("price_level", None),
            ("cuisines", []),
            ("open_at", None),
            ("meal", None),
        ]
        for field, empty in relaxed_candidates:
            if getattr(merged, field) not in (None, [], ""):
                attempted.append(field)
                relaxed_parse = merged.model_copy(deep=True)
                setattr(relaxed_parse, field, empty)
                pool, soft_meta = search(relaxed_parse)
                if pool:
                    effective = relaxed_parse
                    relaxed.append(field)
                    soft_fallback = soft_meta["soft_fallback"]
                    unmet_soft = soft_meta["unmet_soft"]
                    break

    selection: SelectionOutcome | None = None
    if not pool:
        # Deterministic refusal: never let the LLM explain an empty result.
        status = "no_match"
        summary = no_match_summary(merged, attempted)
        picks: list[dict] = []
        picks_map: dict[str, str] = {}
        soft_fallback = False
        unmet_soft = []
        selection_mode = SELECTION_DETERMINISTIC
        candidate_count = 0
        selection_note = ""
    else:
        if relaxed:
            status = "relaxed"
        elif soft_fallback:
            status = "soft_fallback"
        else:
            status = "ok"

        # Constrained LLM re-ranking: the LLM may only choose/order candidates
        # the backend already validated. Any failure -> deterministic order.
        #
        # Trigger on "an LLM is configured", not on the parse path: the parse
        # call can fall back to the keyword parser (timeout/invalid JSON) while
        # the provider is still usable for selection. Only a truly unconfigured
        # backend (demo mode) is always deterministic.
        rerank_enabled = (
            LLM_RERANK_ENABLED if req.rerank is None else bool(req.rerank)
        )
        llm_available = get_provider(config) is not None
        selection_note = ""
        if llm_available and rerank_enabled:
            selection = select_picks(
                pool,
                effective,
                req.limit,
                config,
                req.message,
                relaxed=relaxed,
                soft_fallback=soft_fallback,
                unmet_soft=unmet_soft,
            )
            picks = selection.picks
            selection_mode = selection.selection_mode
            candidate_count = selection.candidate_count
            if selection.selection_mode == SELECTION_FALLBACK:
                selection_note = selection.error or "LLM selection unavailable"
        else:
            picks = pool[: req.limit]
            selection_mode = SELECTION_DETERMINISTIC
            candidate_count = len(pool)

        try:
            if mode == "llm":
                summary, picks_map = explain_llm(
                    config,
                    req.message,
                    effective,
                    picks,
                    relaxed,
                    soft_fallback=soft_fallback,
                    unmet_soft=unmet_soft,
                )
                if not summary:
                    summary, picks_map = demo_summary(
                        req.message,
                        effective,
                        picks,
                        relaxed,
                        soft_fallback=soft_fallback,
                        unmet_soft=unmet_soft,
                    )
            else:
                summary, picks_map = demo_summary(
                    req.message,
                    effective,
                    picks,
                    relaxed,
                    soft_fallback=soft_fallback,
                    unmet_soft=unmet_soft,
                )
        except Exception:
            summary, picks_map = demo_summary(
                req.message,
                effective,
                picks,
                relaxed,
                soft_fallback=soft_fallback,
                unmet_soft=unmet_soft,
            )

        if relaxed:
            # Guarantee disclosure even if the LLM ignored the instruction.
            disclosure = relaxation_disclosure(relaxed)
            if disclosure.lower() not in summary.lower():
                summary = f"{summary.rstrip()} {disclosure}"

        if effective.allergens:
            # Safety disclosure: make it explicit that allergen exclusion happened.
            safety = allergen_disclosure(effective.allergens)
            if safety.lower() not in summary.lower():
                summary = f"{summary.rstrip()} {safety}"

        if soft_fallback:
            # Guarantee the LLM explicitly states that no restaurant matched all
            # soft preferences.
            note = soft_fallback_disclosure(unmet_soft)
            if note.lower() not in summary.lower():
                summary = f"{summary.rstrip()} {note}"

    selection_reasons = selection.reasons if selection else {}
    out_picks = []
    for s in picks:
        rid = s["restaurant"]["id"]
        # LLM selection reasons (validated) are the most specific; the explanation
        # layer and deterministic match reasons are fallbacks.
        reason = (
            selection_reasons.get(rid)
            or picks_map.get(rid)
            or "; ".join(s["reasons"])
        )
        c = card(s["restaurant"], reason)
        c["matched"] = s["reasons"]
        c["soft_mismatches"] = s.get("soft_mismatches", [])
        out_picks.append(c)

    return ChatResponse(
        structured=merged,
        effective=effective,
        mode=mode,
        provider_label=PROVIDER_INFO.get(config.get("provider", "none"), {}).get("label", config.get("provider", "")),
        status=status,
        soft_fallback=soft_fallback,
        unmet_soft=unmet_soft,
        relaxed=relaxed,
        selection_mode=selection_mode,
        candidate_count=candidate_count,
        selection_note=selection_note,
        summary=summary,
        picks=out_picks,
    )
