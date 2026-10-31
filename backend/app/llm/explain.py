"""Generate the explanation layer: LLM-written when configured, otherwise
deterministic templates (demo mode).

Empty results are never delegated to the LLM: `no_match_summary()` produces a
deterministic refusal so an infeasible request can never be presented as if it
had been satisfied. Relaxation, when explicitly opted into, is always disclosed.
"""
from __future__ import annotations

from ..schemas import ParseResult
from .providers import get_provider

EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentences addressing the user's request: what you picked overall, how it fits their meal/time/budget/dietary constraints, and any useful tips.",
        },
        "picks": {
            "type": "object",
            "description": "Keys are restaurant ids from the provided list",
            "properties": {},
        },
    },
    "required": ["summary", "picks"],
}

# Internal filter field -> human label used in disclosures/refusals.
_FIELD_LABELS = {
    "price_level": "price",
    "dietary": "dietary",
    "cuisines": "cuisine",
    "open_at": "opening time",
    "meal": "meal",
}


def constraint_labels(p: ParseResult) -> list[str]:
    """Human-readable list of the hard filters a request applied."""
    labels: list[str] = []
    if p.meal:
        labels.append(f"meal={p.meal}")
    if p.price_level:
        labels.append(f"price={'$' * p.price_level}")
    if p.cuisines:
        labels.append("cuisine=" + "/".join(p.cuisines))
    if p.open_at:
        labels.append(f"open at {p.open_at}")
    if p.dietary:
        labels.append("dietary=" + "+".join(p.dietary))
    if p.avoid:
        labels.append("avoid=" + "/".join(p.avoid))
    return labels


def relaxation_disclosure(relaxed: list[str]) -> str:
    """Explicit disclosure appended whenever filters were relaxed."""
    labels = [_FIELD_LABELS.get(f, f) for f in relaxed]
    return (
        f"Note: no restaurant matched all filters, so I relaxed the "
        f"{' & '.join(labels)} filter(s) — these picks may not meet that constraint."
    )


def no_match_summary(p: ParseResult, attempted: list[str] | None = None) -> str:
    """Deterministic refusal used whenever ranking returns no picks.

    This is deliberately not delegated to the LLM: an empty result must always
    produce an explicit, non-hallucinated refusal.
    """
    attempted = attempted or []
    labels = constraint_labels(p)
    if labels:
        text = (
            "No suitable restaurant found. None of the restaurants around HKU match all of "
            f"your constraints ({', '.join(labels)})."
        )
    else:
        text = (
            "No suitable restaurant found. I could not match your request to any restaurant "
            "around HKU."
        )
    if attempted:
        tried = " & ".join(_FIELD_LABELS.get(f, f) for f in attempted)
        text += f" I tried relaxing the {tried} filter(s) one at a time, but still found no match."
    else:
        text += " I did not relax any filters automatically."
    text += (
        " Try relaxing one of the constraints yourself — for example raise the price level, "
        "drop a dietary requirement, or choose a different meal — and ask again."
    )
    return text


def explain_llm(
    config: dict,
    message: str,
    p: ParseResult,
    picks: list[dict],
    relaxed: list[str] | None = None,
) -> tuple[str, dict[str, str]]:
    provider = get_provider(config)
    if provider is None:
        return demo_summary(message, p, picks, relaxed)

    lines = []
    for pick in picks:
        r = pick["restaurant"]
        lines.append(
            f"- id={r['id']} | {r['name']} ({r['cuisine']}, {r['area']}, avg ${r['avg_cost']}, "
            f"rating {r['rating']}/5, {r['walk_minutes']} min walk) | options: "
            + ", ".join(r.get("tags", [])[:5])
        )
    lines.append("")
    lines.append("Matched filters: " + p.model_dump_json())
    if relaxed:
        relaxed_labels = ", ".join(_FIELD_LABELS.get(f, f) for f in relaxed)
        lines.append(
            "IMPORTANT: these results required relaxing the following filter(s): "
            f"{relaxed_labels}. State this trade-off explicitly in the summary."
        )
    user = (
        "You are a food recommender for HKU students. For each restaurant below, explain in ONE "
        "sentence why it suits the user's request referenced from the matched filters, being honest "
        "about trade-offs (e.g. price, distance). Return ONLY JSON: {summary: string, picks: {id: reason}} "
        "with a key for EVERY restaurant id or empty object if none.\n\n"
        + f"<user_request>{message}</user_request>\n"
        + "<restaurants>\n" + "\n".join(lines) + "</restaurants>"
    )
    system = (
        "Reply with ONLY a JSON object conforming exactly to the schema. "
        "Keep every reason under 40 words. Casual, helpful tone."
    )
    data = provider.chat_json(system, user, EXPLAIN_SCHEMA, max_tokens=900)
    return str(data.get("summary", "")), {k: str(v) for k, v in (data.get("picks") or {}).items()}


def demo_summary(
    message: str,
    p: ParseResult,
    picks: list[dict],
    relaxed: list[str] | None = None,
) -> tuple[str, dict[str, str]]:
    relaxed = relaxed or []
    if not picks:
        return no_match_summary(p), {}
    labels = []
    if p.meal:
        labels.append(p.meal)
    if p.price_level:
        labels.append({1: "budget", 2: "mid-range", 3: "upscale"}[p.price_level])
    if p.cuisines:
        labels.append("/".join(p.cuisines))
    if p.open_at:
        labels.append(f"open at {p.open_at}")
    if p.dietary:
        labels.append("+".join(p.dietary))
    qualifier = " · ".join(labels) if labels else "your request"
    top = picks[0]["restaurant"]
    summary = (
        f"Here are {len(picks)} spot(s) around HKU for {qualifier}. "
        f"Top pick: **{top['name']}** ({top['cuisine']}, ~{top['avg_cost']} HKD, "
        f"{top['walk_minutes']} min walk, {top['rating']}/5). "
    )
    if relaxed:
        summary += relaxation_disclosure(relaxed) + " "
    picks_map = {pick["restaurant"]["id"]: "; ".join(pick["reasons"]) for pick in picks}
    return summary, picks_map
