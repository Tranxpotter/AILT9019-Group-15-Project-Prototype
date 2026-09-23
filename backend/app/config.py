"""Central paths & constants for the HKU Bites backend."""
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
