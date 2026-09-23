"""Pillow-based dummy image generation: hero photo, interior photo and menu image
for every restaurant. Every image carries the restaurant's name so correctness of
image selection is visually verifiable."""
import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import IMAGES_DIR, IMAGES_URL_PREFIX
from .seed_data import RESTAURANTS

FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu/"),
    Path("/usr/share/fonts/truetype/liberation/"),
    Path("/usr/share/fonts/"),
]
FONT_NAMES = {
    "bold": ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf"],
    "regular": ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf"],
}


def _find_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONT_DIRS:
        for name in FONT_NAMES[kind]:
            p = d / name
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()

FONT_CACHE: dict[tuple, ImageFont.FreeTypeFont] = {}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    key = (kind, size)
    if key not in FONT_CACHE:
        FONT_CACHE[key] = _find_font(kind, size)
    return FONT_CACHE[key]


def _palette(seed: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    rnd = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))
    c1 = tuple(rnd.randint(30, 70) for _ in range(3))
    c2 = tuple(rnd.randint(120, 200) for _ in range(3))
    accent = (255, 214, 120)
    return (c1, c2, accent)


def _gradient(size: tuple[int, int], c1, c2) -> Image.Image:
    w, h = size
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        px = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
        img.putpixel((0, y), px)
    return img.resize((w, h))


def _center_text(draw: ImageDraw.ImageDraw, xy, text, fnt, fill, anchor="mm"):
    draw.text(xy, text, font=fnt, fill=fill, anchor=anchor)


def _name_label(draw: ImageDraw.ImageDraw, w: int, name: str, cuisine: str) -> int:
    """Draw restaurant name + cuisine; returns bottom y so other art avoids it."""
    draw.rounded_rectangle((24, 20, w - 24, 104), radius=14, fill=(0, 0, 0, 140))
    # Pillow RGBA overlay needs separate pass; keep it simple with dark fill
    return 108


def _plate(draw, cx, cy, radius, plate_color, food_colors, rnd):
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=plate_color)
    inner = int(radius * 0.72)
    draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=tuple(min(255, c + 25) for c in plate_color))
    for _ in range(7):
        ang = rnd.uniform(0, 6.283)
        d = rnd.uniform(0, inner * 0.55)
        r = rnd.uniform(inner * 0.12, inner * 0.26)
        px = cx + d * 0.8
        py = cy + d * 0.55
        draw.ellipse((px - r, py - r * 0.7, px + r, py + r * 0.7), fill=rnd.choice(food_colors))
    # garnish dots
    for _ in range(10):
        px = cx + rnd.uniform(-inner * 0.8, inner * 0.8)
        py = cy + rnd.uniform(-inner * 0.55, inner * 0.55)
        draw.ellipse((px - 4, py - 4, px + 4, py + 4), fill=(60, 140, 90))


def generate_hero(restaurant: dict) -> Path:
    slug = restaurant["id"]
    path = IMAGES_DIR / f"{slug}-hero.png"
    w, h = 800, 500
    c1, c2, accent = _palette(slug)
    img = _gradient((w, h), c1, c2)
    draw = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(slug)

    # soft light blobs
    for _ in range(4):
        px = rnd.randint(0, w); py = rnd.randint(0, h)
        r = rnd.randint(90, 220)
        blob = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        bd = ImageDraw.Draw(blob)
        bd.ellipse((px - r, py - r, px + r, py + r), fill=(255, 255, 255, 26))
        img = Image.alpha_composite(img.convert("RGBA"), blob)

    draw = ImageDraw.Draw(img, "RGBA")
    _plate(draw, 560, 300, 150, tuple(rnd.randint(230, 250) for _ in range(3)),
           [(220, 90, 70), (235, 170, 60), (110, 160, 90), (200, 130, 80)], rnd)

    # chopsticks mock
    draw.line((430, 470, 620, 350), fill=(222, 184, 135), width=10)
    draw.line((450, 480, 640, 360), fill=(205, 165, 115), width=10)

    # label chip with name
    draw.rounded_rectangle((28, 28, 560, 128), radius=18, fill=(15, 15, 25, 200))
    _center_text(draw, (294, 62), restaurant["name"], font("bold", 40), (255, 255, 255))
    _center_text(draw, (294, 102), f"{restaurant['cuisine']}  •  sample dish photo", font("regular", 22), (255, 214, 120))
    _center_text(draw, (w // 2, h - 24), "HKU Bites — synthetic image (generated)", font("regular", 16), (255, 255, 255, 170))

    img.convert("RGB").save(path)
    return path


def generate_interior(restaurant: dict) -> Path:
    slug = restaurant["id"]
    path = IMAGES_DIR / f"{slug}-interior.png"
    w, h = 800, 500
    c1, c2, accent = _palette(slug + "-in")
    img = _gradient((w, h), tuple(int(v * 0.55) for v in c1), tuple(int(v * 0.7) for v in c2))
    draw = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(slug + "-in")

    # pendant lights
    for px in (160, 400, 640):
        draw.line((px, 0, px, 120), fill=(60, 60, 60), width=6)
        draw.ellipse((px - 26, 120, px + 26, 172), fill=(50, 50, 50))
        draw.ellipse((px - 14, 132, px + 14, 160), fill=(255, 236, 170))

    # tables + chairs
    for ty in (270, 400):
        draw.rounded_rectangle((180, ty, 620, ty + 60), radius=12, fill=(120, 80, 50), outline=(90, 60, 40), width=3)
        for tx in (230, 570):
            draw.rounded_rectangle((tx - 24, ty - 46, tx + 24, ty - 6), radius=10, fill=(80, 60, 60))
            draw.rounded_rectangle((tx - 24, ty + 66, tx + 24, ty + 106), radius=10, fill=(80, 60, 60))

    # wall art
    draw.rounded_rectangle((60, 200, 150, 290), radius=8, fill=(255, 255, 255, 60))
    draw.rounded_rectangle((650, 200, 740, 290), radius=8, fill=(255, 255, 255, 40))

    draw.rounded_rectangle((28, 28, 520, 118), radius=18, fill=(15, 15, 25, 200))
    _center_text(draw, (274, 62), restaurant["name"], font("bold", 38), (255, 255, 255))
    _center_text(draw, (274, 100), f"{restaurant['area']}  •  sample interior photo", font("regular", 20), (255, 214, 120))
    _center_text(draw, (w // 2, h - 24), "HKU Bites — synthetic image (generated)", font("regular", 16), (255, 255, 255, 170))
    img.convert("RGB").save(path)
    return path


def generate_menu(restaurant: dict) -> Path:
    slug = restaurant["id"]
    path = IMAGES_DIR / f"{slug}-menu.png"
    w, h = 700, 980
    img = Image.new("RGB", (w, h), (250, 246, 238))
    draw = ImageDraw.Draw(img, "RGBA")

    draw.rectangle((18, 18, w - 18, h - 18), outline=(180, 130, 70), width=4)
    _center_text(draw, (w // 2, 78), restaurant["name"], font("bold", 44), (70, 45, 20))
    _center_text(draw, (w // 2, 122), f"{restaurant['cuisine']}  —  {restaurant['area']}", font("regular", 22), (140, 100, 60))
    draw.line((60, 150, w - 60, 150), fill=(180, 130, 70), width=2)

    y = 190
    items = restaurant.get("menu", [])
    current_cat = None
    for item in items:
        if item.get("category") != current_cat:
            current_cat = item.get("category")
            _center_text(draw, (w // 2, y + 14), current_cat.upper(), font("bold", 24), (160, 90, 40))
            y += 48
        price = f"${item.get('price', 0)}"
        draw.text((60, y), item["name"], font=font("bold", 24), fill=(45, 35, 25))
        draw.text((w - 60 - draw.textlength(price, font=font("bold", 24)), y), price, font=font("bold", 24), fill=(45, 35, 25))
        desc = item.get("description", "")
        draw.text((60, y + 32), desc[:64], font=font("regular", 17), fill=(120, 110, 95))
        draw.line((60, y + 64, w - 60, y + 64), fill=(225, 210, 185), width=1)
        y += 78
        if y > h - 90:
            break

    _center_text(draw, (w // 2, h - 48), "Sample menu — generated for demo (not a real venue)", font("regular", 18), (150, 130, 100))
    img.save(path)
    return path


def generate_all() -> list[Path]:
    """Generate all images for all restaurants (idempotent). Returns new paths."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for r in RESTAURANTS:
        for fn in (generate_hero, generate_interior, generate_menu):
            p = fn(r)
            created.append(p)
    return created


def ensure_images() -> list[Path]:
    """Generate only the images that are missing; returns paths generated now."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for r in RESTAURANTS:
        for fn in (generate_hero, generate_interior, generate_menu):
            p = IMAGES_DIR / f"{r['id']}-{fn.__name__.replace('generate_', '')}.png"
            if not p.exists():
                missing.append(fn(r))
    return missing


def image_urls_for(restaurant: dict) -> dict[str, str]:
    slug = restaurant.get("id", "")
    return {
        "hero": f"{IMAGES_URL_PREFIX}/{slug}-hero.png",
        "interior": f"{IMAGES_URL_PREFIX}/{slug}-interior.png",
        "menu": f"{IMAGES_URL_PREFIX}/{slug}-menu.png",
    }
