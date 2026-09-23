"""HKU Bites — FastAPI application entry point."""
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .config import DATA_DIR, IMAGES_DIR, RESTAURANTS_JSON
from .images import ensure_images
from .routers import chat, llm_config, memory, restaurants
from .seed_data import RESTAURANTS

app = FastAPI(
    title="HKU Bites API",
    description="Restaurant recommendation API around HKU (synthetic demo data).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(restaurants.router)
app.include_router(chat.router)
app.include_router(llm_config.router)
app.include_router(memory.router)

app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")


@app.on_event("startup")
def startup() -> None:
    db.init_db()
    if not db.list_restaurants():
        db.upsert_restaurants(RESTAURANTS)
    ensure_images()
    # keep a human-readable JSON snapshot in sync with the DB
    try:
        RESTAURANTS_JSON.write_text(
            json.dumps(RESTAURANTS, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


@app.get("/api/health")
def health():
    return {"ok": True, "restaurants": len(db.list_restaurants())}


# ---- Optional: serve the built frontend (production mode) ----
_DIST = DATA_DIR.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/")
    def index():
        return FileResponse(str(_DIST / "index.html"))

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = _DIST / path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))
