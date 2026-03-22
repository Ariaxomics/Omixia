#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$SCRIPT_DIR/../backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_$TIMESTAMP"

# Load MONGO_PASSWORD from backend/.env if not already set
if [ -z "${MONGO_PASSWORD:-}" ]; then
  ENV_FILE="$SCRIPT_DIR/../backend/.env"
  if [ -f "$ENV_FILE" ]; then
    MONGO_PASSWORD=$(grep -E '^MONGO_INITDB_ROOT_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
  fi
fi

if [ -z "${MONGO_PASSWORD:-}" ]; then
  echo "ERROR: MONGO_PASSWORD not set and could not be read from backend/.env" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup $BACKUP_NAME ..."

docker exec mongo_omixia mongodump \
  --username admin \
  --password "$MONGO_PASSWORD" \
  --authenticationDatabase admin \
  --out "/tmp/$BACKUP_NAME"

docker cp "mongo_omixia:/tmp/$BACKUP_NAME" "$BACKUP_DIR/$BACKUP_NAME"

# Clean up temp dump inside container
docker exec mongo_omixia rm -rf "/tmp/$BACKUP_NAME"

echo "[$(date)] Backup complete: $BACKUP_DIR/$BACKUP_NAME"

# Optional: remove backups older than 30 days
find "$BACKUP_DIR" -maxdepth 1 -name "backup_*" -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
