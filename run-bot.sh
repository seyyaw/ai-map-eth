#!/usr/bin/env bash
# Start the AI-MAP Telegram bot (long polling: no public IP or TLS needed).
#
#   AIMAP_BOT_TOKEN=... ./run-bot.sh
#
# Writes to the SAME database as the collection server.
set -euo pipefail
cd "$(dirname "$0")"

export AIMAP_DB="${AIMAP_DB:-$PWD/tools/data/aimap.db}"

if [[ -z "${AIMAP_BOT_TOKEN:-}" ]]; then
  echo "AIMAP_BOT_TOKEN is not set. Get one from @BotFather on Telegram." >&2
  exit 1
fi

PY="./.venv/bin/python"
[[ -x "$PY" ]] || { echo "No .venv. Run: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2; exit 1; }

echo "database: $AIMAP_DB"
exec "$PY" tools/telegram_bot/bot.py
