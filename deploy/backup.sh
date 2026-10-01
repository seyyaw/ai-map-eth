#!/usr/bin/env bash
# Nightly backup of the response database.
#   0 2 * * *  /srv/aimap/deploy/backup.sh
#
# Uses sqlite3 .backup, which is safe against a live writer (plain cp is not).
set -euo pipefail
DB="${AIMAP_DB:-/srv/aimap/tools/data/aimap.db}"
DEST="${AIMAP_BACKUP_DIR:-/srv/aimap/backups}"
KEEP_DAYS="${AIMAP_BACKUP_KEEP:-30}"

mkdir -p "$DEST"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$DEST/aimap-$STAMP.db"

sqlite3 "$DB" ".backup '$OUT'"
gzip -9 "$OUT"
echo "backed up to $OUT.gz"

find "$DEST" -name 'aimap-*.db.gz' -mtime "+$KEEP_DAYS" -delete
