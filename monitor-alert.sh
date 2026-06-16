#!/usr/bin/env bash
set -euo pipefail

BASE="/root/codex-automations"
LOG="$BASE/logs/monitor-alert.log"
PATH_PREFIX="/root/.local/bin:/root/.codex/packages/standalone/current/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export PATH="$PATH_PREFIX${PATH:+:$PATH}"

mkdir -p "$BASE/logs"
cd "$BASE"

{
  echo "===== $(date '+%F %T') monitor-alert start ====="
  python3 "$BASE/monitor-alert.py"
  echo "===== $(date '+%F %T') monitor-alert done ====="
} >> "$LOG" 2>&1
