#!/usr/bin/env bash
# Start everything with one command: collection server (survey + dashboard) and
# the Telegram bot, both writing to the SAME database.
#
#   ./run-all.sh
#   AIMAP_BOT_TOKEN='123456:ABC...' ./run-all.sh
#   PORT=9000 HOST=0.0.0.0 ./run-all.sh
#
# The two processes MUST share one SQLite file. run_all.py resolves that path
# once and exports it into both children, so they cannot drift apart.
# Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 tools/run_all.py "$@"
