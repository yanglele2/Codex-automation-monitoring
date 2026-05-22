#!/usr/bin/env bash
set -euo pipefail

JOB="$1"
BASE="/root/codex-automations"
PROMPT="$BASE/prompts/$JOB.md"
LOG="$BASE/logs/$JOB.log"
STATE_DIR="$BASE/state"
TODAY="$(date '+%F')"
DONE_MARKER="$STATE_DIR/$JOB-$TODAY.done"
TIMEOUT_SECONDS="${CODEX_JOB_TIMEOUT_SECONDS:-14400}"
RUN_OUTPUT="$(mktemp "/tmp/codex-$JOB-$TODAY-XXXXXX.log")"

case "$JOB" in
  earnings-vertical-compare)
    TIMEOUT_SECONDS="${CODEX_JOB_TIMEOUT_SECONDS:-21600}"
    ;;
esac

[ -f "$PROMPT" ] || { echo "Missing prompt: $PROMPT"; exit 1; }
mkdir -p "$STATE_DIR"

exec 9>/tmp/codex-$JOB.lock
flock -n 9 || exit 0

if [ -f "$DONE_MARKER" ] || { [ -f "$LOG" ] && grep -q "^===== $TODAY .* $JOB done =====" "$LOG"; }; then
  echo "===== $(date '+%F %T') $JOB skipped: already done today =====" >> "$LOG"
  touch "$DONE_MARKER"
  exit 0
fi

cd "$BASE"

{
  echo "===== $(date '+%F %T') $JOB start ====="
  if ! timeout "$TIMEOUT_SECONDS" codex exec --full-auto --skip-git-repo-check < "$PROMPT" > "$RUN_OUTPUT" 2>&1; then
    cat "$RUN_OUTPUT"
    echo "===== $(date '+%F %T') $JOB retry ====="
    sleep 60
    timeout "$TIMEOUT_SECONDS" codex exec --full-auto --skip-git-repo-check < "$PROMPT" > "$RUN_OUTPUT" 2>&1
  fi
  cat "$RUN_OUTPUT"
  echo "===== $(date '+%F %T') $JOB validation start ====="
  "$BASE/validate-output.sh" "$JOB" "$RUN_OUTPUT"
  echo "===== $(date '+%F %T') $JOB done ====="
  touch "$DONE_MARKER"
} >> "$LOG" 2>&1
