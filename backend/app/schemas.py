"""Pydantic request/response models shared by the API."""
from typing import Optional

from pydantic import BaseModel, Field


class ParseResult(BaseModel):
    """Structured filters extracted from a chat message (by an LLM or fallback)."""
    meal: Optional[str] = Field(default=None, description="breakfast | lunch | dinner | snack, or null")
    cuisines: list[str] = Field(default_factory=list)
    price_level: Optional[int] = Field(default=None, description="1 ($), 2 ($$), 3 ($$$), or null")
    open_at: Optional[str] = Field(default=None, description="'HH:MM' the user plans to eat, or null")
    dietary: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    notes: str = Field(default="", description="extra context the model detected")


class ChatRequest(BaseModel):
    message: str
    filters: Optional[ParseResult] = None  # pre-existing UI filter selections merged in
    limit: int = 5
    relax: bool = Field(
        default=False,
        description=(
            "Opt-in: if no restaurant satisfies every hard filter, drop one filter at a time "
            "and disclose which filters were relaxed. Defaults to false (strict)."
        ),
    )


class ChatResponse(BaseModel):
    structured: ParseResult
    effective: Optional[ParseResult] = Field(
        default=None,
        description="Filters actually applied when ranking (differs from structured only when relaxed).",
    )
    mode: str  # "llm" | "demo"
    provider_label: str
    status: str = Field(default="ok", description="ok | relaxed | no_match")
    relaxed: list[str] = Field(default_factory=list)
    summary: str
    picks: list[dict]  # {restaurant, reason}


class TestLLMResponse(BaseModel):
    ok: bool
    detail: str


class LLMConfigIn(BaseModel):
    provider: str
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.3
