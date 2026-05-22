#!/usr/bin/env bash
set -euo pipefail

BASE="/root/codex-automations"
LOG="$BASE/logs/dashboard.log"
PIDFILE="$BASE/state/dashboard.pid"

mkdir -p "$BASE/logs" "$BASE/state"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    exit 0
  fi
fi

setsid -f python3 "$BASE/dashboard/server.py" >> "$LOG" 2>&1
sleep 1
pgrep -f "$BASE/dashboard/server.py" | head -n 1 > "$PIDFILE"
