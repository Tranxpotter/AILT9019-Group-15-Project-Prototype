# 🍜 HKU Bites — Restaurant Recommender around HKU

A full-stack prototype that recommends restaurants around the HKU campus from
natural-language instructions (or quick filter chips). Built for the AILT9019
project; **all restaurant data, reviews and images are synthetic/dummy**,
generated for testing.

## Features

- **💬 Chat recommender** — type *"cheap halal lunch, no pork, near Water Street"*
  and get structured filters → deterministic ranking → LLM-written explanation.
- **⚡ Quick filters** — meal (breakfast/lunch/dinner/snack), cost ($/$$/$$$),
  cuisine, dietary (vegetarian/vegan/halal/no-pork/gluten-free/nut-free),
  **allergens** (seafood/fish/shellfish/peanut/tree-nut/gluten/dairy/egg/soy/
  sesame), "eating at HH:MM" (overnight hours handled). Selections are sent as
  context with chat.
- **🗺️ Map + detail UI** — Leaflet + OpenStreetMap, price-colored markers, HKU
  campus marker, restaurant popups; detail view with dummy photos (restaurant
  name burned in), generated menu poster, menu list and synthetic reviews.
- **⚙️ LLM configuration** — pick OpenAI, Anthropic Claude, Google Gemini,
  DeepSeek, Ollama/LM Studio (local), or **any custom OpenAI-compatible endpoint**
  (LM Studio, vLLM, OpenRouter, proxies…). Test connection + save from the UI.
  Without an LLM the app runs in **demo mode** with a built-in keyword parser.
- **🔌 Data API** — REST endpoints expose restaurant data, filters, chat
  and LLM config for the LLM/frontend to consume.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.14 · FastAPI · Uvicorn · httpx (raw provider calls) · Pillow |
| Data | SQLite (`backend/data/hku_bites.db`) + JSON snapshot (`data/restaurants.json`) |
| Images | Generated PNGs (hero/interior/menu) with the restaurant name rendered in |
| Frontend | React 18 · Vite · Leaflet + OpenStreetMap tiles |

## Project layout

```text
AILT9019-Project-Prototype2/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app (mounts /images + built frontend)
│   │   ├── db.py             # SQLite schema + data access
│   │   ├── seed_data.py      # 10 synthetic restaurants around HKU
│   │   ├── images.py         # Pillow generators (hero/interior/menu)
│   │   ├── recommend.py      # deterministic filter + scoring engine
│   │   ├── schemas.py        # Pydantic models
│   │   ├── llm/
│   │   │   ├── providers.py  # OpenAI-compat / Anthropic / Gemini adapters
│   │   │   ├── parse.py      # chat -> structured filters (LLM + keyword fallback)
│   │   │   └── explain.py    # recommendation explanations (LLM + template)
│   │   └── routers/          # restaurants, chat, llm-config
│   ├── scripts/
│   │   ├── init_db.py            # seed DB + generate images + JSON snapshot
│   │   ├── generate_images.py    # (re)generate Pillow images only
│   │   ├── test_llm_providers.py # mock-server unit tests for the 3 provider shapes
│   │   └── test_chat_e2e.py      # end-to-end LLM chat through the API (mock endpoint)
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   ├── api.js
    │   ├── styles.css
    │   └── components/       # Header, FilterChips, ChatBox, MapView,
    │                         # RestaurantList, RestaurantDetail, LLMConfigModal,
    │                         # RecommendationCard
    └── vite.config.js        # proxies /api + /images to :8010
```

## Setup & run

> Port 8000 was already taken in this environment, so the project uses **8010**.

### 1. Backend

```bash
cd backend
python3 -m venv .venv                 # once
.venv/bin/pip install -r requirements.txt   # once
.venv/bin/python scripts/init_db.py   # once: seeds 10 restaurants + 30 images
.venv/bin/uvicorn app.main:app --port 8010 --reload
```

Startup is also self-seeding (idempotent) if you skip `init_db.py`.

### 2. Frontend (dev mode)

```bash
cd frontend
npm install               # once (use --cache .npmcache if ~/.npm is unwritable)
npm run dev               # http://localhost:5173 (proxies API to :8010)
```

### One-command runs

```bash
./run_backend.sh    # seeds (if needed) + starts API at http://127.0.0.1:8010
./run_frontend.sh   # starts Vite at http://127.0.0.1:5173
```

### Production-ish mode (optional)

```bash
cd frontend && npm run build     # creates frontend/dist
cd ../backend && .venv/bin/uvicorn app.main:app --port 8010
# FastAPI then serves the built SPA itself at http://127.0.0.1:8010
```

## Configuring an LLM

Click **⚙️ LLM Config** in the header:

| Provider | Base URL (default) | Example model | Key |
|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | required |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | required |
| Anthropic | `https://api.anthropic.com` | `claude-3-5-sonnet-latest` | required |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | `gemini-2.0-flash` | required |
| Ollama | `http://localhost:11434/v1` | `llama3.1` | not needed |
| Custom | any OpenAI-compatible URL | any | as needed |

Use **Test connection** before saving. Save, then the header pill switches to
`⚡ provider: model` and chat responses are labeled *LLM mode*.

### How the two LLM calls work

1. **Parse**: your message + current filter chips → strict JSON
   (`meal`, `cuisines`, `price_level`, `open_at`, `dietary`, `keywords`, `avoid`).
   OpenAI-compatible endpoints use `response_format: json_object`;
   Anthropic uses a forced `tool_use`; Gemini uses `responseSchema`.
2. **Explain**: the ranked candidates + parsed filters → `{summary, picks:{id: reason}}`.

Ranking itself is **deterministic in the backend** (`recommend.py`) so results
stay reproducible; the LLM never queries the DB directly. If parsing fails or no
LLM is configured, the built-in keyword parser + template explanations kick in
(demo mode).

### Honest empty results (no silent relaxation)

Ranking is strict on hard constraints: a restaurant is returned only if it
satisfies **every** hard filter (meal, price, opening time, allergens, avoided
features). If nothing matches, `/api/chat` returns `status: "no_match"`, an empty
`picks` list, and a deterministic summary beginning **"No suitable restaurant
found."** The LLM is never asked to explain an empty result, so it cannot invent
a recommendation.

Relaxation is opt-in only: send `"relax": true` and the backend will drop one
non-safety hard filter at a time. The response then sets `status: "relaxed"`,
lists the dropped fields in `relaxed`, and both Demo and LLM summaries explicitly
disclose the trade-off.

### Soft preferences: strict first, disclosed fallback

Dietary labels and cuisine are **soft preferences**. The backend returns only
restaurants that satisfy every hard constraint **and** every soft preference
when such a restaurant exists. If none does, it falls back to hard-constraint
matches and explicitly says so in the summary (`status: "soft_fallback"`,
`soft_fallback: true`, `unmet_soft: ["dietary"|"cuisines"]`). Fallback cards
carry `soft_mismatches` so the UI can show which preference is unmet.

Keywords remain ranking signals for now; richer preference matching (e.g.
"soup noodles") is Phase 2.

Soft preferences are also enriched deterministically: explicit dish/cuisine
words (curry→Indian, sushi→Japanese, noodles→Noodles, dessert→Desserts, dim
sum→Dim Sum, ...) are added to `cuisines` even if the LLM omits them, and
explicit diet phrases (vegan, halal, no pork, nut-free, gluten-free, ...) are
added to `dietary`. This keeps soft gating consistent across models.

### Full meals vs. snacks

For **breakfast / lunch / dinner** requests, dessert and snack venues are
excluded even if they list that meal or are open at that time. Requests for
**snack** or **dessert** still return them. This is a hard filter, applied before
soft-preference ranking.

### Safety: allergens are enforced deterministically

Allergies are safety-critical, so they are not left to the LLM. The backend
extracts allergen phrases from the message (e.g. "no seafood", "shellfish
allergy"), normalizes them to canonical groups (fish, crustacean, mollusk,
peanut, tree-nut, gluten, dairy, egg, soy, sesame), and hard-excludes any venue
whose metadata or menu text indicates that allergen. Allergen flags are
conservative: if an ingredient synonym appears anywhere in a venue's text, the
venue is excluded. Allergen filters are **never** relaxed by the opt-in
relaxation mode.

The UI exposes allergen chips under **Quick filters**, and chat summaries
disclose which allergens were excluded for safety. `avoid` remains for soft
dislikes; allergen-like entries in `avoid` are promoted to the safety layer.
The main recommendation cards/list do not show per-venue allergen warnings;
clicking a restaurant opens the detail view with the `⚠️ Contains: ...` note.
Chat summaries still disclose allergen exclusions for safety.

**Dietary labels vs allergens.** `dietary` is for venue preferences/certifications
(vegetarian, vegan, halal, no-pork, gluten-free kitchen, nut-free kitchen).
`allergens` are safety exclusions based on detected ingredients (fish, crustacean,
mollusk, peanut, tree-nut, gluten, dairy, egg, soy, sesame). Allergy phrasing
("allergic to nuts", "celiac", "shellfish allergy") populates `allergens` only;
explicit diet phrasing ("nut-free", "gluten-free") populates `dietary` only.
Saying both applies both intentionally. The backend also reconciles LLM output:
a redundant dietary label (e.g. `nut-free` + `peanut`/`tree-nut`) is dropped for
an allergy request unless the user explicitly asked for that certification.

## API overview

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + restaurant count |
| GET | `/api/meta` | meals, cuisines, dietary + allergen options, map centre |
| GET | `/api/restaurants` | filtered list (meal/cuisine/price/dietary/allergens/open_at/q) + `soft_fallback`/`unmet_soft` |
| GET | `/api/restaurants/{id}` | full detail: menu, reviews, images |
| POST | `/api/chat` | `{message, filters?, limit?, relax?}` → picks + summary + `status`/`soft_fallback`/`unmet_soft`/`relaxed` (filters include `allergens`) |
| GET/PUT | `/api/llm-config` | read / save LLM settings |
| GET | `/api/llm-config/providers` | provider catalog with defaults |
| POST | `/api/llm-config/test` | connectivity test with submitted settings |
| GET | `/images/*` | generated dummy photos / menus |

## Synthetic data notes

- **10 restaurants** around Sai Ying Pun / Sheung Wan / Kennedy Town with
  plausible (fictional) names, cuisines, opening hours (incl. overnight),
  menus with prices, ratings and 3 synthetic reviews each.
- **30 generated images** (hero, interior, menu poster per venue) — each carries
  the restaurant's name so you can verify correct image selection.
- Nothing here is a real venue; addresses are approximate.

## Tests

```bash
cd backend
.venv/bin/python scripts/test_llm_providers.py   # provider wire formats (mock servers)
.venv/bin/python scripts/test_no_match.py        # strict refusal / disclosed relaxation (M1)
.venv/bin/python scripts/test_allergens.py       # deterministic allergen safety (Phase 1)
.venv/bin/python scripts/test_soft_preferences.py # strict-first soft preferences + fallback
# requires backend running on :8010:
.venv/bin/python scripts/test_chat_e2e.py        # full LLM chat path (mock endpoint)
```
