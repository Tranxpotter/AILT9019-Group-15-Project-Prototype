"""Generate the dummy database (SQLite) + synthetic images + JSON snapshot."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import IMAGES_DIR, RESTAURANTS_JSON  # noqa: E402
from app.images import generate_all  # noqa: E402
from app.seed_data import RESTAURANTS  # noqa: E402


def main() -> None:
    db.init_db()
    db.upsert_restaurants(RESTAURANTS)
    created = generate_all()
    RESTAURANTS_JSON.write_text(
        json.dumps(RESTAURANTS, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    rows = db.list_restaurants()
    print(f"Seeded {len(rows)} restaurants into {db.DB_PATH}")
    print(f"Generated {len(created)} images in {IMAGES_DIR}")
    for r in rows:
        print(f"  - {r['name']} ({r['cuisine']}, {r['area']}, {r['walk_minutes']} min walk)")


if __name__ == "__main__":
    main()
