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

PHOTO_TAR=""
if [ -d "$PHOTOS" ] && [ -n "$(ls -A "$PHOTOS" 2>/dev/null || true)" ]; then
  tar -C "$ROOT" -czf "${DEST}/product-images-${stamp}.tar.gz" product-images
  find "$DEST" -name 'product-images-*.tar.gz' -mtime +14 -delete
  PHOTO_TAR="${DEST}/product-images-${stamp}.tar.gz"
  echo "Wrote ${PHOTO_TAR}"
fi

# Optional off-box copy. Set BACKUP_REMOTE to a directory or rsync target
# (user@host:/path). Local backup still succeeds if this copy fails.
if [ -n "${BACKUP_REMOTE:-}" ]; then
  if [ -d "$BACKUP_REMOTE" ]; then
    cp "${DEST}/eshop-${stamp}.db" "$BACKUP_REMOTE/" || echo "WARN: could not copy database to $BACKUP_REMOTE" >&2
    if [ -n "$PHOTO_TAR" ]; then
      cp "$PHOTO_TAR" "$BACKUP_REMOTE/" || echo "WARN: could not copy photos to $BACKUP_REMOTE" >&2
    fi
  elif command -v rsync >/dev/null 2>&1; then
    rsync -a "${DEST}/eshop-${stamp}.db" ${PHOTO_TAR:+"$PHOTO_TAR"} "$BACKUP_REMOTE/" \
      || echo "WARN: rsync to $BACKUP_REMOTE failed" >&2
  else
    echo "WARN: BACKUP_REMOTE is set but rsync is not installed" >&2
  fi
fi
