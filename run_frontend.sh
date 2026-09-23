#!/usr/bin/env bash
# Start the HKU Bites frontend (Vite dev server, proxies /api + /images to :8010).
set -e
cd "$(dirname "$0")/frontend"
npm install --no-audit --no-fund --cache .npmcache >/dev/null 2>&1 || true
echo "Frontend: http://127.0.0.1:5173"
exec npm run dev
