#!/usr/bin/env bash
# Start the HKU Bites backend (seeds DB + images on first run).
set -e
cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  echo "Creating virtualenv…"
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python scripts/init_db.py >/dev/null 2>&1 || true

echo "Backend: http://127.0.0.1:8010  (API docs: /docs)"
exec .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
