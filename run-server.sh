#!/usr/bin/env bash
# Start the AI-MAP collection server (serves the web questionnaire + API).
#
#   ./run-server.sh                 listen on 127.0.0.1:8000
#   PORT=9000 ./run-server.sh       different port
#   HOST=0.0.0.0 ./run-server.sh    listen on all interfaces (put a TLS proxy in front)
#
# Requires AIMAP_ADMIN_TOKEN. The admin endpoints refuse to serve without it.
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
export AIMAP_DB="${AIMAP_DB:-$PWD/tools/data/aimap.db}"

if [[ -z "${AIMAP_ADMIN_TOKEN:-}" ]]; then
  echo "AIMAP_ADMIN_TOKEN is not set." >&2
  echo "Generate one:  export AIMAP_ADMIN_TOKEN=\$(openssl rand -hex 32)" >&2
  exit 1
fi

PY="./.venv/bin/python"
[[ -x "$PY" ]] || { echo "No .venv. Run: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2; exit 1; }

echo "database : $AIMAP_DB"
echo "listening: http://$HOST:$PORT"
exec "$PWD/.venv/bin/uvicorn" --app-dir tools/server app:app \
     --host "$HOST" --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
