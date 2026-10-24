"""Chat endpoint: parse -> deterministic rank -> explain."""
from fastapi import APIRouter

from .. import db
from ..llm.explain import demo_summary, explain_llm
from ..llm.parse import parse_message
from ..llm.providers import PROVIDER_INFO
from ..recommend import card, filter_and_score
from ..schemas import ChatRequest, ChatResponse, ParseResult

router = APIRouter(prefix="/api", tags=["chat"])


def _merge(ui: ParseResult | None, parsed: ParseResult) -> ParseResult:
    """UI-selected filters take precedence over message-parsed ones."""
    if ui is None:
        return parsed
    return ParseResult(
        meal=ui.meal or parsed.meal,
        cuisines=ui.cuisines or parsed.cuisines,
        price_level=ui.price_level or parsed.price_level,
        open_at=ui.open_at or parsed.open_at,
        dietary=ui.dietary or parsed.dietary,
        keywords=parsed.keywords or [],
        avoid=list(dict.fromkeys(ui.avoid + parsed.avoid)),
        notes=parsed.notes,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    config = db.get_llm_config()
    parsed, mode = parse_message(config, req.message)
    merged = _merge(req.filters, parsed)

    restaurants = db.list_restaurants()

    def search(pr):
        return filter_and_score(restaurants, pr)[: req.limit]

    picks = search(merged)
    effective = merged
    relaxed: list[str] = []
    if not picks:
        # gentle relaxation: drop one constraint at a time until something fits
        relaxed_candidates = [
            ("price_level", None),
            ("dietary", []),
            ("cuisines", []),
            ("open_at", None),
            ("meal", None),
        ]
        for field, empty in relaxed_candidates:
            if getattr(merged, field) not in (None, [], ""):
                relaxed_parse = merged.model_copy(deep=True)
                setattr(relaxed_parse, field, empty)
                picks = search(relaxed_parse)
                if picks:
                    effective = relaxed_parse
                    relaxed.append(field)
                    break

    # explain (LLM when available, template otherwise)
    try:
        if mode == "llm":
            summary, picks_map = explain_llm(config, req.message, effective, picks)
            if not summary:
                summary, picks_map = demo_summary(req.message, effective, picks, relaxed)
                mode = "llm"
        else:
            summary, picks_map = demo_summary(req.message, effective, picks, relaxed)
    except Exception:
        summary, picks_map = demo_summary(req.message, effective, picks, relaxed)

    out_picks = []
    for s in picks:
        reason = picks_map.get(s["restaurant"]["id"]) or "; ".join(s["reasons"])
        c = card(s["restaurant"], reason)
        c["matched"] = s["reasons"]
        out_picks.append(c)

    return ChatResponse(
        structured=merged,
        mode=mode,
        provider_label=PROVIDER_INFO.get(config.get("provider", "none"), {}).get("label", config.get("provider", "")),
        summary=summary,
        picks=out_picks,
    )
