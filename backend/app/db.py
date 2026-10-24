"""SQLite persistence: schema, connection, and small data-access helpers."""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from .config import DB_PATH, IMAGES_URL_PREFIX

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurants (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    cuisine         TEXT NOT NULL,
    cuisine_tags    TEXT NOT NULL DEFAULT '[]',
    meal_categories TEXT NOT NULL DEFAULT '[]',
    price_level     INTEGER NOT NULL,
    avg_cost        INTEGER NOT NULL,
    rating          REAL NOT NULL,
    review_count    INTEGER NOT NULL DEFAULT 0,
    address         TEXT NOT NULL,
    area            TEXT NOT NULL,
    lat             REAL NOT NULL,
    lng             REAL NOT NULL,
    walk_minutes    INTEGER NOT NULL,
    dietary         TEXT NOT NULL DEFAULT '[]',
    tags            TEXT NOT NULL DEFAULT '[]',
    opening         TEXT NOT NULL DEFAULT '[]',
    description     TEXT NOT NULL DEFAULT '',
    hero_image      TEXT NOT NULL DEFAULT '',
    interior_image  TEXT NOT NULL DEFAULT '',
    menu_image      TEXT NOT NULL DEFAULT '',
    menu            TEXT NOT NULL DEFAULT '[]',
    reviews         TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS llm_config (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    provider    TEXT NOT NULL DEFAULT 'none',
    api_key     TEXT NOT NULL DEFAULT '',
    base_url    TEXT NOT NULL DEFAULT '',
    model       TEXT NOT NULL DEFAULT '',
    temperature REAL NOT NULL DEFAULT 0.3,
    updated_at  TEXT NOT NULL DEFAULT ''
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO llm_config (id, provider, updated_at) VALUES (1, 'none', ?)",
            (now_iso(),),
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------- restaurants ----------------

def _loads(v: Optional[str]) -> Any:
    if not v:
        return None
    try:
        return json.loads(v)
    except (json.JSONDecodeError, TypeError):
        return None


def row_to_restaurant(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in (
        "cuisine_tags",
        "meal_categories",
        "dietary",
        "tags",
        "opening",
        "menu",
        "reviews",
    ):
        d[key] = _loads(d.get(key)) or []
    return d


def upsert_restaurants(restaurants: list[dict]) -> None:
    cols = (
        "id,name,cuisine,cuisine_tags,meal_categories,price_level,avg_cost,rating,"
        "review_count,address,area,lat,lng,walk_minutes,dietary,tags,opening,"
        "description,hero_image,interior_image,menu_image,menu,reviews"
    )
    with get_conn() as conn:
        for r in restaurants:
            slug = r.get("id", "")
            vals = [
                r.get("id"),
                r.get("name"),
                r.get("cuisine"),
                json.dumps(r.get("cuisine_tags", []), ensure_ascii=False),
                json.dumps(r.get("meal_categories", []), ensure_ascii=False),
                r.get("price_level", 2),
                r.get("avg_cost", 0),
                r.get("rating", 0.0),
                r.get("review_count", 0),
                r.get("address", ""),
                r.get("area", ""),
                r.get("lat", 0.0),
                r.get("lng", 0.0),
                r.get("walk_minutes", 0),
                json.dumps(r.get("dietary", []), ensure_ascii=False),
                json.dumps(r.get("tags", []), ensure_ascii=False),
                json.dumps(r.get("opening", []), ensure_ascii=False),
                r.get("description", ""),
                r.get("hero_image") or f"{IMAGES_URL_PREFIX}/{slug}-hero.png",
                r.get("interior_image") or f"{IMAGES_URL_PREFIX}/{slug}-interior.png",
                r.get("menu_image") or f"{IMAGES_URL_PREFIX}/{slug}-menu.png",
                json.dumps(r.get("menu", []), ensure_ascii=False),
                json.dumps(r.get("reviews", []), ensure_ascii=False),
            ]
            n_cols = len(cols.split(","))
            placeholders = ",".join("?" * n_cols)
            conn.execute(
                f"INSERT INTO restaurants ({cols}) VALUES ({placeholders}) "
                "ON CONFLICT(id) DO UPDATE SET "
                + ",".join(f"{c}=excluded.{c}" for c in cols.split(",") if c != "id"),
                vals,
            )


def list_restaurants() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM restaurants").fetchall()
    return [row_to_restaurant(r) for r in rows]


def get_restaurant(restaurant_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM restaurants WHERE id = ?", (restaurant_id,)
        ).fetchone()
    return row_to_restaurant(row) if row else None


# ---------------- llm config ----------------

def get_llm_config() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM llm_config WHERE id = 1").fetchone()
    return dict(row) if row else {"provider": "none", "api_key": "", "base_url": "", "model": ""}


def save_llm_config(cfg: dict) -> dict:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO llm_config (id, provider, api_key, base_url, model, temperature, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET provider=excluded.provider, api_key=excluded.api_key, "
            "base_url=excluded.base_url, model=excluded.model, temperature=excluded.temperature, "
            "updated_at=excluded.updated_at",
            (
                cfg.get("provider", "none"),
                cfg.get("api_key", ""),
                cfg.get("base_url", ""),
                cfg.get("model", ""),
                float(cfg.get("temperature", 0.3)),
                now_iso(),
            ),
        )
    return get_llm_config()
