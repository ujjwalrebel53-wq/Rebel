#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$ROOT/.venv" ]]; then
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  (cd "$ROOT/frontend" && npm install)
fi

echo "Starting Rebel backend on :8000 and UI on :5173"
echo "Ensure Copilot proxy is running (see README)"

trap 'kill 0' EXIT
"$ROOT/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --app-dir "$ROOT/backend" &
(cd "$ROOT/frontend" && npm run dev) &
wait
