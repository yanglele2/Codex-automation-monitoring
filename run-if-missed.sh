#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 JOB HH:MM DAYS WINDOW_MINUTES" >&2
  exit 2
fi

JOB="$1"
SCHEDULE_TIME="$2"
DAYS="$3"
WINDOW_MINUTES="$4"

BASE="/root/codex-automations"
LOG="$BASE/logs/$JOB.log"
TODAY="$(date '+%F')"
DONE_MARKER="$BASE/state/$JOB-$TODAY.done"
NOW_EPOCH="$(date '+%s')"
SCHEDULE_EPOCH="$(date -d "$TODAY $SCHEDULE_TIME" '+%s')"
CURRENT_DOW="$(date '+%u')"

if [ "$DAYS" != "*" ] && ! [[ ",$DAYS," == *",$CURRENT_DOW,"* ]]; then
  exit 0
fi

if [ "$NOW_EPOCH" -lt "$SCHEDULE_EPOCH" ]; then
  exit 0
fi

WINDOW_END=$((SCHEDULE_EPOCH + WINDOW_MINUTES * 60))
if [ "$NOW_EPOCH" -gt "$WINDOW_END" ]; then
  exit 0
fi

if [ -f "$DONE_MARKER" ] || { [ -f "$LOG" ] && grep -q "^===== $TODAY .* $JOB done =====" "$LOG"; }; then
  exit 0
fi

echo "===== $(date '+%F %T') $JOB missed check triggered =====" >> "$LOG"
exec "$BASE/run.sh" "$JOB"
