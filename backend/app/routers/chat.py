"""Chat endpoint: parse -> deterministic rank -> explain."""
from fastapi import APIRouter

from .. import db
from ..allergens import allergens_from_terms, normalize_allergens
from ..llm.explain import (
    allergen_disclosure,
    demo_summary,
    explain_llm,
    no_match_summary,
    relaxation_disclosure,
    soft_fallback_disclosure,
)
from ..llm.parse import parse_message
from ..llm.providers import PROVIDER_INFO
from ..recommend import card, filter_and_score, split_soft_matches
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
    return ParseResult(
        meal=base.meal or parsed.meal,
        cuisines=cuisines,
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

    def search(pr):
        scored = filter_and_score(restaurants, pr)
        selected, meta = split_soft_matches(scored, pr)
        return selected[: req.limit], meta

    # Hard constraints are strict by default: never silently relax them.
    # Soft preferences (dietary, cuisine) are strict first; if none match, we
    # fall back to hard-only matches and disclose the fallback.
    picks, soft_meta = search(merged)
    effective = merged
    relaxed: list[str] = []
    attempted: list[str] = []
    soft_fallback = soft_meta["soft_fallback"]
    unmet_soft = soft_meta["unmet_soft"]

    if not picks and req.relax:
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
                picks, soft_meta = search(relaxed_parse)
                if picks:
                    effective = relaxed_parse
                    relaxed.append(field)
                    soft_fallback = soft_meta["soft_fallback"]
                    unmet_soft = soft_meta["unmet_soft"]
                    break

    if not picks:
        # Deterministic refusal: never let the LLM explain an empty result.
        status = "no_match"
        summary = no_match_summary(merged, attempted)
        picks_map: dict[str, str] = {}
        soft_fallback = False
        unmet_soft = []
    else:
        if relaxed:
            status = "relaxed"
        elif soft_fallback:
            status = "soft_fallback"
        else:
            status = "ok"

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

    out_picks = []
    for s in picks:
        reason = picks_map.get(s["restaurant"]["id"]) or "; ".join(s["reasons"])
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
        summary=summary,
        picks=out_picks,
    )
