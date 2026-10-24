"""LLM configuration CRUD + connectivity test."""
from fastapi import APIRouter

from .. import db
from ..llm.providers import (
    DEFAULT_BASE_URLS,
    LLMError,
    PROVIDER_INFO,
    get_provider,
)
from ..schemas import LLMConfigIn, TestLLMResponse

router = APIRouter(prefix="/api/llm-config", tags=["llm-config"])


def _config_response(cfg: dict) -> dict:
    """Normalize a stored config into the API shape (adds api_key_masked + configured)."""
    has_key = bool(cfg.get("api_key"))
    key = cfg.get("api_key", "")
    return {
        **cfg,
        "api_key_masked": ("•••" + key[-4:]) if has_key and len(key) > 4 else ("set" if has_key else ""),
        "configured": cfg.get("provider") != "none" and bool(cfg.get("model")),
    }


@router.get("")
def get_config():
    return _config_response(db.get_llm_config())


@router.get("/providers")
def provider_catalog():
    return PROVIDER_INFO


@router.put("")
def save_config(cfg: LLMConfigIn):
    cleaned = cfg.model_dump()
    cleaned["provider"] = (cleaned["provider"] or "none").strip()
    cleaned["model"] = cleaned["model"].strip()
    cleaned["base_url"] = cleaned["base_url"].strip()
    cleaned["api_key"] = cleaned["api_key"].strip()
    if cleaned["provider"] != "none" and not cleaned["model"]:
        cleaned["provider"] = "none"
    return _config_response(db.save_llm_config(cleaned))


@router.post("/test", response_model=TestLLMResponse)
def test_config(cfg: LLMConfigIn):
    """Try a 1-token round-trip with the SUBMITTED config (does not persist)."""
    try:
        provider = get_provider(cfg.model_dump())
        if provider is None:
            return TestLLMResponse(ok=False, detail="No model set — nothing to test. Demo mode active.")
        reply = provider.ping()
        return TestLLMResponse(ok=True, detail=f"Connected. Model replied: {reply[:60]!r}")
    except LLMError as e:
        return TestLLMResponse(ok=False, detail=str(e))
    except Exception as e:  # noqa: BLE001 - surface anything to the UI
        return TestLLMResponse(ok=False, detail=f"Unexpected error: {e}")
