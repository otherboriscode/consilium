#!/bin/bash
# Consilium daily backup → Backblaze B2 via restic.
#
# Reads B2 credentials + RESTIC_REPOSITORY + RESTIC_PASSWORD from
# /etc/consilium/.env. Run via systemd timer (see deploy/systemd/
# consilium-backup.{service,timer}).
#
# Retention: 7 daily / 4 weekly / 6 monthly. Verifies 5% of data each
# run so corruption surfaces within a week.

set -euo pipefail
set -a
# shellcheck disable=SC1091
source /etc/consilium/.env
set +a

LOCK_FILE=/tmp/consilium-backup.lock
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "consilium-backup: another instance is running, exiting"
    exit 0
fi

# Backup data dir + immutable config
restic backup \
    /var/lib/consilium \
    /etc/consilium/limits.yaml \
    --tag consilium-daily \
    --exclude "*.tmp" \
    --exclude "*.lock"

# Retention: 7 daily, 4 weekly, 6 monthly — prune in same call so
# repository shrinks immediately.
restic forget \
    --keep-daily 7 \
    --keep-weekly 4 \
    --keep-monthly 6 \
    --prune

# Verify a sample of data each day so silent corruption surfaces fast.
restic check --read-data-subset=5%

echo "consilium-backup: completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
