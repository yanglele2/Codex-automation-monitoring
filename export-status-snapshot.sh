#!/usr/bin/env bash
set -euo pipefail

BASE="/root/codex-automations"
SNAPSHOT="$BASE/status-snapshot.json"
LOG="$BASE/logs/status-snapshot.log"

mkdir -p "$BASE/logs"
cd "$BASE"

{
  echo "===== $(date '+%F %T') status snapshot start ====="
  python3 "$BASE/export-status-snapshot.py" > "$SNAPSHOT.tmp"
  mv "$SNAPSHOT.tmp" "$SNAPSHOT"
  git add status-snapshot.json
  if git diff --cached --quiet -- status-snapshot.json; then
    echo "no snapshot changes"
  else
    git commit -m "Update automation status snapshot"
    git push
  fi
  echo "===== $(date '+%F %T') status snapshot done ====="
} >> "$LOG" 2>&1
