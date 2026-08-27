#!/bin/bash
# Nightly SQLite + listing-photo copy. Example cron (root):
#   15 3 * * * /opt/eshop/deploy/backup.sh
set -euo pipefail

ROOT="${DATA_DIR:-/var/lib/eshop}"
SRC="$ROOT/eshop.db"
PHOTOS="$ROOT/product-images"
DEST="$ROOT/backups"
mkdir -p "$DEST"

if [ ! -f "$SRC" ]; then
  echo "No database at $SRC yet"
  exit 0
fi

stamp=$(date -u +%Y%m%dT%H%M%SZ)
sqlite3 "$SRC" ".backup '${DEST}/eshop-${stamp}.db'"
find "$DEST" -name 'eshop-*.db' -mtime +14 -delete
echo "Wrote ${DEST}/eshop-${stamp}.db"

if [ -d "$PHOTOS" ] && [ -n "$(ls -A "$PHOTOS" 2>/dev/null || true)" ]; then
  tar -C "$ROOT" -czf "${DEST}/product-images-${stamp}.tar.gz" product-images
  find "$DEST" -name 'product-images-*.tar.gz' -mtime +14 -delete
  echo "Wrote ${DEST}/product-images-${stamp}.tar.gz"
fi
