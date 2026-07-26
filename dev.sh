#!/usr/bin/env bash
# BharatBeat dev runner — starts BOTH:
#   backend  (FastAPI)  → http://localhost:8000   (API docs at /docs)
#   frontend (Vite)     → http://localhost:5173
#
# Usage:   ./dev.sh          (Ctrl-C stops both)
# Reseed:  ./dev.sh --seed   (drops + reseeds the DB first, then starts)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"

if [[ "${1:-}" == "--seed" ]]; then
  echo "↻ reseeding database…"
  ( cd "$ROOT/backend" && "$PY" -m scripts.seed ) || { echo "seed failed — is Postgres up?"; exit 1; }
fi

# Free the ports in case a previous run is still bound.
pkill -f "uvicorn main:app" 2>/dev/null
pkill -f "node.*vite"       2>/dev/null
sleep 1

echo "▶ backend  → http://localhost:8000  (docs: /docs)"
( cd "$ROOT/backend" && "$PY" -m uvicorn main:app --port 8000 ) &
BACK=$!

echo "▶ frontend → http://localhost:5173"
( cd "$ROOT/frontend" && npm run dev ) &
FRONT=$!

# Ctrl-C (or TERM) tears down both, including any child reloader/worker procs.
trap 'echo; echo "stopping…"; kill $BACK $FRONT 2>/dev/null; \
      pkill -f "uvicorn main:app" 2>/dev/null; pkill -f "node.*vite" 2>/dev/null; exit 0' INT TERM

wait
