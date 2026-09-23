"""Regenerate only the Pillow images (hero/interior/menu) for all restaurants."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.images import generate_all  # noqa: E402


def main() -> None:
    created = generate_all()
    print(f"Generated {len(created)} images")
    for p in created:
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
