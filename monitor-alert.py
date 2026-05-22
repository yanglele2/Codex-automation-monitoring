#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
import tempfile
import textwrap
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path("/root/codex-automations")
ALERT_STATE = BASE / "state" / "alerts"
ALERT_LOG = BASE / "logs" / "monitor-alert.log"
SNAPSHOT = BASE / "status-snapshot.json"
DASHBOARD_URL = "http://127.0.0.1:8765/api/status"
NOTION_PROJECT_URL = "https://www.notion.so/fbc627d633af442c961069c0006cbc2f?pvs=21"
COOLDOWN_SECONDS = 4 * 60 * 60


def now() -> dt.datetime:
    return dt.datetime.now()


def log(message: str) -> None:
    timestamp = now().strftime("%F %T")
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ALERT_LOG.open("a") as handle:
        handle.write(f"===== {timestamp} monitor-alert {message} =====\n")


def load_dashboard() -> tuple[dict | None, str | None]:
    try:
        with urllib.request.urlopen(DASHBOARD_URL, timeout=5) as response:
            if response.status != 200:
                return None, f"dashboard returned HTTP {response.status}"
            return json.loads(response.read().decode()), None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return None, str(exc)


def snapshot_age_issue() -> dict | None:
    if not SNAPSHOT.exists():
        return {
            "key": "snapshot-missing",
            "severity": "warning",
            "title": "状态快照文件不存在",
            "detail": f"未找到 {SNAPSHOT}",
        }
    age = (now().timestamp() - SNAPSHOT.stat().st_mtime)
    if age > 5 * 60 * 60:
        return {
            "key": "snapshot-stale",
            "severity": "warning",
            "title": "远程状态快照超过 5 小时未更新",
            "detail": f"status-snapshot.json age={int(age)} seconds",
        }
    return None


def collect_issues() -> list[dict]:
    issues: list[dict] = []
    status, error = load_dashboard()
    if error:
        issues.append({
            "key": "dashboard-down",
            "severity": "critical",
            "title": "本地监控面板不可用",
            "detail": f"{DASHBOARD_URL} failed: {error}",
        })
    elif status:
        if not status.get("cron_in_sync", False):
            issues.append({
                "key": "crontab-not-in-sync",
                "severity": "warning",
                "title": "系统 crontab 与模板不一致",
                "detail": "crontab -l 与 crontab.with-catchup 不一致",
            })
        for job in status.get("jobs", []):
            if job.get("status") in {"failed", "warning"}:
                validation = job.get("last_validation") or {}
                issues.append({
                    "key": f"job-{job.get('job')}-{job.get('status')}",
                    "severity": "critical" if job.get("status") == "failed" else "warning",
                    "title": f"{job.get('label') or job.get('job')} 状态异常：{job.get('status')}",
                    "detail": validation.get("detail") or f"log={job.get('log_path')}",
                    "job": job.get("job"),
                    "last_start": job.get("last_start"),
                    "last_done": job.get("last_done"),
                    "log_path": job.get("log_path"),
                })

    stale = snapshot_age_issue()
    if stale:
        issues.append(stale)
    return issues


def alert_key(issue: dict) -> str:
    raw = json.dumps({"key": issue.get("key"), "title": issue.get("title")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def marker_path(issue: dict) -> Path:
    ALERT_STATE.mkdir(parents=True, exist_ok=True)
    return ALERT_STATE / f"{alert_key(issue)}.json"


def should_send(issue: dict) -> bool:
    marker = marker_path(issue)
    current = now().timestamp()
    if marker.exists():
        try:
            previous = json.loads(marker.read_text())
            if current - float(previous.get("sent_at_epoch", 0)) < COOLDOWN_SECONDS:
                return False
        except Exception:
            pass
    return True


def mark_sent(issue: dict) -> None:
    marker = marker_path(issue)
    current = now().timestamp()
    marker.write_text(json.dumps({"sent_at_epoch": current, "issue": issue}, ensure_ascii=False, indent=2))


def build_prompt(issues: list[dict]) -> str:
    payload = json.dumps(issues, ensure_ascii=False, indent=2)
    return textwrap.dedent(f"""
    你是自动化任务监控告警 Agent。请立即在 Notion 中创建一条告警提醒。

    目标位置：优先写入或创建在这个金融项目页面下的「自动化任务告警」数据库：
    {NOTION_PROJECT_URL}

    如果该数据库不存在，请在该页面下创建一个普通告警页面也可以。告警内容必须包含：
    - 标题：`自动化任务告警 - YYYY-MM-DD HH:mm`
    - 严重程度：critical 或 warning
    - 状态：open
    - AI总结：用 1-3 句中文说明故障
    - 正文：列出每个 issue 的 key、title、detail、job、last_start、last_done、log_path

    告警 issues JSON：
    ```json
    {payload}
    ```

    只允许写入 Notion 告警提醒。不要修改本地文件、脚本、prompt、crontab 或任何自动化配置。
    写入后请读取或重新查询告警页面，确认已落库，并在最终输出里给出 Notion 页面链接。
    """).strip()


def send_notion_alert(issues: list[dict]) -> int:
    prompt = build_prompt(issues)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
        handle.write(prompt)
        prompt_path = Path(handle.name)
    try:
        with prompt_path.open("r") as stdin:
            result = subprocess.run(
                ["codex", "exec", "--full-auto", "--skip-git-repo-check"],
                cwd=str(BASE),
                stdin=stdin,
                text=True,
                capture_output=True,
                timeout=1800,
            )
        log(f"notion alert exit={result.returncode}")
        with ALERT_LOG.open("a") as handle:
            handle.write(result.stdout)
            handle.write(result.stderr)
            handle.write("\n")
        return result.returncode
    finally:
        prompt_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    issues = collect_issues()
    if args.dry_run:
        print(json.dumps({"issues": issues, "sendable": issues}, ensure_ascii=False, indent=2))
        return 0
    sendable = [issue for issue in issues if should_send(issue)]
    if not sendable:
        log("ok")
        return 0
    log(f"sending {len(sendable)} alert(s)")
    result = send_notion_alert(sendable)
    if result == 0:
        for issue in sendable:
            mark_sent(issue)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
