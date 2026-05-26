#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 JOB RUN_OUTPUT_LOG" >&2
  exit 2
fi

JOB="$1"
RUN_OUTPUT="$2"

[ -f "$RUN_OUTPUT" ] || { echo "validation failed: missing run output: $RUN_OUTPUT" >&2; exit 1; }

count_pattern() {
  local pattern="$1"
  grep -E -c "$pattern" "$RUN_OUTPUT" || true
}

has_pattern() {
  local pattern="$1"
  grep -E -q "$pattern" "$RUN_OUTPUT"
}

CREATE_COUNT="$(count_pattern 'mcp: codex_apps/notion_notion-create-pages \(completed\)')"
NOTION_READ_COUNT="$(count_pattern 'mcp: codex_apps/notion_(fetch|search|notion-query-data-sources) \(completed\)')"
NOTION_WRITE_OR_UPDATE_COUNT="$(count_pattern 'mcp: codex_apps/notion_.*(create|update|patch|append|edit).* \(completed\)')"
LAST_WRITE_LINE="$(grep -nE 'mcp: codex_apps/notion_.*(create|update|patch|append|edit).* \(completed\)' "$RUN_OUTPUT" | tail -n 1 | cut -d: -f1 || true)"

if has_pattern '已落地到配置文件|更新定时模板|安装系统 crontab|diff --git|apply patch|patch: completed'; then
  echo "validation failed: run appears to have changed automation/configuration instead of only business data" >&2
  exit 1
fi

if has_pattern 'Traceback|UnhandledPromiseRejection|ValidationError|Permission denied|Error: failed to initialize|Mcp error: -32000'; then
  echo "validation failed: run output contains hard failure keywords" >&2
  exit 1
fi

require_creates() {
  local min_count="$1"
  if [ "$CREATE_COUNT" -lt "$min_count" ]; then
    echo "validation failed: expected at least $min_count Notion page create(s), got $CREATE_COUNT" >&2
    exit 1
  fi
}

require_notion_read() {
  if [ "$NOTION_READ_COUNT" -lt 1 ]; then
    echo "validation failed: expected at least one completed Notion read/search verification" >&2
    exit 1
  fi
}

require_post_write_readback() {
  if [ -z "$LAST_WRITE_LINE" ]; then
    return 0
  fi
  if ! awk -v start="$LAST_WRITE_LINE" 'NR > start && /mcp: codex_apps\/notion_(fetch|search|notion-query-data-sources) \(completed\)/ { found=1 } END { exit found ? 0 : 1 }' "$RUN_OUTPUT"; then
    echo "validation failed: expected a completed Notion read/search after the last Notion write" >&2
    exit 1
  fi
}

allow_explicit_noop() {
  has_pattern '没有候选记录|没有找到.*候选|无.*候选|未检索到.*高置信度|按规则跳过|无需更新|数据一致|报告不存在|非.*交易日|暂无高质量机会|无重大消息'
}

case "$JOB" in
  financial-news)
    require_creates 4
    require_notion_read
    ;;
  stock-crypto-fundamentals)
    require_creates 1
    require_notion_read
    ;;
  sector-trend-data)
    require_creates 1
    require_notion_read
    ;;
  sector-rotation)
    require_creates 3
    require_notion_read
    ;;
  us-sector-opportunity)
    if [ "$CREATE_COUNT" -lt 1 ] && ! allow_explicit_noop; then
      echo "validation failed: expected at least one opportunity record or an explicit no-op reason" >&2
      exit 1
    fi
    require_notion_read
    ;;
  earnings-search)
    if [ "$CREATE_COUNT" -lt 1 ] && ! allow_explicit_noop; then
      echo "validation failed: expected at least one earnings record or an explicit no-candidate reason" >&2
      exit 1
    fi
    require_notion_read
    ;;
  earnings-vertical-compare)
    if [ "$NOTION_WRITE_OR_UPDATE_COUNT" -lt 1 ] && ! allow_explicit_noop; then
      echo "validation failed: expected a Notion comparison update/create or an explicit no-candidate reason" >&2
      exit 1
    fi
    require_notion_read
    ;;
  sector-trend-us-close-review)
    if [ "$NOTION_WRITE_OR_UPDATE_COUNT" -lt 1 ] && ! allow_explicit_noop; then
      echo "validation failed: expected a Notion update or an explicit no-op reason" >&2
      exit 1
    fi
    if ! allow_explicit_noop; then
      require_notion_read
    fi
    ;;
  *)
    if [ "$CREATE_COUNT" -lt 1 ] && [ "$NOTION_WRITE_OR_UPDATE_COUNT" -lt 1 ] && ! allow_explicit_noop; then
      echo "validation failed: no completed Notion write/update and no explicit no-op reason" >&2
      exit 1
    fi
    require_notion_read
    ;;
esac

require_post_write_readback

echo "validation passed: create_count=$CREATE_COUNT notion_read_count=$NOTION_READ_COUNT notion_write_or_update_count=$NOTION_WRITE_OR_UPDATE_COUNT"
