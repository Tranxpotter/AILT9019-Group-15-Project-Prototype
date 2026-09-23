"""Generate the explanation layer: LLM-written when configured, otherwise
deterministic templates (demo mode)."""
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


def explain_llm(config: dict, message: str, p: ParseResult, picks: list[dict]) -> tuple[str, dict[str, str]]:
    provider = get_provider(config)
    if provider is None:
        return demo_summary(message, p, picks)

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


def demo_summary(message: str, p: ParseResult, picks: list[dict], relaxed: list[str] | None = None) -> tuple[str, dict[str, str]]:
    relaxed = relaxed or []
    if not picks:
        return (
            "I could not find a restaurant that fits all your constraints. "
            "Try relaxing the price, meal or time filters."
        ), {}
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
        summary += f"(I relaxed the {' & '.join(relaxed)} filter(s) to find these.) "
    picks_map = {pick["restaurant"]["id"]: "; ".join(pick["reasons"]) for pick in picks}
    return summary, picks_map
