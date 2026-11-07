"""Central paths & constants for the HKU Bites backend."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
DB_PATH = DATA_DIR / "hku_bites.db"
RESTAURANTS_JSON = DATA_DIR / "restaurants.json"
SEED_JSON_PATH = DATA_DIR / "restaurants.json"

# URL prefix under which /images are served by FastAPI
IMAGES_URL_PREFIX = "/images"

# ---- Allowed values (shared with the LLM parse schema + frontend) ----
MEALS = ["breakfast", "lunch", "dinner", "snack"]
PRICE_LEVELS = {
    1: "$",
    2: "$$",
    3: "$$$",
}
DIETARY_OPTIONS = [
    "vegetarian",
    "vegan",
    "halal",
    "no-pork",
    "gluten-free",
    "nut-free",
]
CUISINES = [
    "Cantonese",
    "Dim Sum",
    "Noodles",
    "Western",
    "Indian",
    "Nepalese",
    "Thai",
    "Japanese",
    "Korean",
    "Italian",
    "Mediterranean",
    "Healthy",
    "Salads",
    "Burgers",
    "Steak",
    "Desserts",
    "Hong Kong Style",
    "Vietnamese",
    "Malaysian",
    "Vegetarian",
    "Mexican",
]


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except (TypeError, ValueError):
        return default


# ---- Constrained LLM re-ranking (Phase 3) ----
# The LLM may only reorder/select from backend-generated candidates; the backend
# always validates its output and falls back to the deterministic order.
LLM_RERANK_ENABLED = _env_flag("LLM_RERANK_ENABLED", True)
# How many candidates (top-K) are offered to the selector.
LLM_RERANK_POOL = max(1, _env_int("LLM_RERANK_POOL", 15))
# Hard wall-clock budget for the selector call before falling back.
LLM_RERANK_TIMEOUT_SECONDS = max(0.5, _env_float("LLM_RERANK_TIMEOUT_SECONDS", 20.0))
