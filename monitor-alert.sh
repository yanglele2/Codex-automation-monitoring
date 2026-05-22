#!/usr/bin/env bash
set -euo pipefail

BASE="/root/codex-automations"
LOG="$BASE/logs/monitor-alert.log"

mkdir -p "$BASE/logs"
cd "$BASE"

{
  echo "===== $(date '+%F %T') monitor-alert start ====="
  python3 "$BASE/monitor-alert.py"
  echo "===== $(date '+%F %T') monitor-alert done ====="
} >> "$LOG" 2>&1
