#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path("/root/codex-automations")
LOG_DIR = BASE / "logs"
STATE_DIR = BASE / "state"
CRON_TEMPLATE = BASE / "crontab.with-catchup"
DASHBOARD_DIR = BASE / "dashboard"

JOB_LABELS = {
    "financial-news": "金融消息",
    "earnings-search": "财报搜集",
    "stock-crypto-fundamentals": "个股/币种基本面",
    "sector-trend-data": "板块走势数据",
    "sector-trend-us-close-review": "美股收盘复查",
    "sector-rotation": "板块轮动",
    "earnings-vertical-compare": "财报纵向对比",
    "us-sector-opportunity": "美股机会洞察",
}

LINE_RE = re.compile(r"^===== (?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}) (?P<job>[\w-]+) (?P<event>.+) =====$")
VALIDATION_RE = re.compile(r"validation (passed|failed): (?P<detail>.+)")
PAGE_RE = re.compile(r"https://www\.notion\.so/[^\s)]+")


def read_text(path: Path, max_bytes: int | None = None) -> str:
    try:
        if max_bytes is None:
            return path.read_text(errors="replace")
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
            return handle.read().decode(errors="replace")
    except FileNotFoundError:
        return ""


def current_crontab() -> str:
    try:
        result = subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False, timeout=3)
        return result.stdout
    except Exception as exc:
        return f"# crontab read failed: {exc}\n"


def parse_cron(text: str) -> dict[str, dict]:
    jobs: dict[str, dict] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        minute, hour, _dom, _month, dow, command = parts[:6]
        if command.endswith("/run.sh") and len(parts) >= 7:
            job = parts[6]
            jobs.setdefault(job, {})["schedule"] = {
                "minute": minute,
                "hour": hour,
                "dow": dow,
                "raw": line,
                "label": human_cron_time(minute, hour, dow),
            }
        elif command.endswith("/run-if-missed.sh") and len(parts) >= 10:
            job = parts[6]
            jobs.setdefault(job, {})["catchup"] = {
                "window_minutes": int(parts[9]) if parts[9].isdigit() else None,
                "raw": line,
                "label": f"{parts[7]} 后 {parts[9]} 分钟内每 10 分钟补跑",
            }
    return jobs


def human_cron_time(minute: str, hour: str, dow: str) -> str:
    days = "每天" if dow == "*" else "周二至周六" if dow == "2-6" else dow
    return f"{days} {int(hour):02d}:{int(minute):02d}" if minute.isdigit() and hour.isdigit() else f"{days} {hour}:{minute}"


def parse_dt(date_s: str, time_s: str) -> dt.datetime:
    return dt.datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S")


def tail_lines(text: str, count: int = 80) -> list[str]:
    lines = text.splitlines()
    return lines[-count:]


def latest_events(job: str, log_text: str) -> dict:
    lines = log_text.splitlines()
    starts: list[dt.datetime] = []
    dones: list[dt.datetime] = []
    retries: list[dt.datetime] = []
    skipped: list[dt.datetime] = []
    last_start_index: int | None = None

    for index, line in enumerate(lines):
        match = LINE_RE.match(line)
        if not (match and match.group("job") == job):
            continue
        when = parse_dt(match.group("date"), match.group("time"))
        event = match.group("event")
        if event == "start":
            starts.append(when)
            last_start_index = index
        elif event == "done":
            dones.append(when)
        elif event == "retry":
            retries.append(when)
        elif event.startswith("skipped"):
            skipped.append(when)

    segment = lines[last_start_index:] if last_start_index is not None else lines
    validations: list[dict] = []
    pages: list[str] = []
    config_warning = False
    hard_error = False

    def archival_log_line(line: str) -> bool:
        return line.startswith(("/root/.codex/", "/root/codex-automations/logs/", "./logs/"))

    for line in segment:
        match = LINE_RE.match(line)
        if match and match.group("job") == job:
            when = parse_dt(match.group("date"), match.group("time"))
            event = match.group("event")
            if event == "validation start":
                validations.append({"time": when.isoformat(), "status": "started", "detail": ""})

        if archival_log_line(line):
            continue

        validation = VALIDATION_RE.search(line)
        if validation:
            validations.append({
                "time": None,
                "status": validation.group(1),
                "detail": validation.group("detail"),
            })

        pages.extend(PAGE_RE.findall(line))
        if re.search(r"已落地到配置文件|更新定时模板|安装系统 crontab|diff --git|apply patch|patch: completed", line):
            config_warning = True
        if re.search(r"Traceback|UnhandledPromiseRejection|ValidationError|Permission denied|Error: failed to initialize|failed to run command|No such file or directory|usage limit|You've hit your usage limit", line):
            hard_error = True

    last_start = starts[-1] if starts else None
    last_done = dones[-1] if dones else None
    last_validation = validations[-1] if validations else None
    duration = None
    if last_start and last_done and last_done >= last_start:
        duration = int((last_done - last_start).total_seconds())

    return {
        "last_start": last_start.isoformat() if last_start else None,
        "last_done": last_done.isoformat() if last_done else None,
        "duration_seconds": duration,
        "retry_count": len(retries),
        "skipped_count": len(skipped),
        "last_validation": last_validation,
        "notion_pages": sorted(set(pages))[-12:],
        "config_warning": config_warning,
        "hard_error": hard_error,
        "tail": tail_lines("\n".join(segment)),
    }


def next_run(schedule: dict | None, now: dt.datetime) -> str | None:
    if not schedule:
        return None
    minute = schedule.get("minute")
    hour = schedule.get("hour")
    dow = schedule.get("dow")
    if not (str(minute).isdigit() and str(hour).isdigit()):
        return None
    allowed = set(range(1, 8)) if dow == "*" else {int(x) for x in str(dow).replace("-", ",").split(",") if x.isdigit()}
    if dow == "2-6":
        allowed = set(range(2, 7))
    for offset in range(0, 14):
        candidate_date = (now + dt.timedelta(days=offset)).date()
        candidate = dt.datetime.combine(candidate_date, dt.time(int(hour), int(minute)))
        if candidate <= now:
            continue
        if candidate.isoweekday() in allowed:
            return candidate.isoformat()
    return None


def build_status() -> dict:
    now = dt.datetime.now()
    template_cron = read_text(CRON_TEMPLATE)
    installed_cron = current_crontab()
    cron_jobs = parse_cron(installed_cron or template_cron)
    template_jobs = parse_cron(template_cron)
    jobs = sorted(set(JOB_LABELS) | set(cron_jobs) | set(template_jobs))

    items = []
    today = now.strftime("%F")
    for job in jobs:
        log_path = LOG_DIR / f"{job}.log"
        log_text = read_text(log_path, max_bytes=300_000)
        events = latest_events(job, log_text)
        marker = STATE_DIR / f"{job}-{today}.done"
        prompt = BASE / "prompts" / f"{job}.md"
        schedule = cron_jobs.get(job, {}).get("schedule") or template_jobs.get(job, {}).get("schedule")
        catchup = cron_jobs.get(job, {}).get("catchup") or template_jobs.get(job, {}).get("catchup")

        has_done_today = marker.exists()
        status = "idle"
        if has_done_today:
            status = "passed"
        if events["last_start"] and (not events["last_done"] or events["last_done"] < events["last_start"]):
            status = "running"
        if events["hard_error"] or events["config_warning"]:
            status = "warning" if status == "passed" else "failed"
        validation = events["last_validation"]
        if validation and validation.get("status") == "failed":
            status = "failed"

        items.append({
            "job": job,
            "label": JOB_LABELS.get(job, job),
            "status": status,
            "schedule": schedule,
            "catchup": catchup,
            "next_run": next_run(schedule, now),
            "done_today": has_done_today,
            "done_marker": str(marker),
            "prompt_exists": prompt.exists(),
            "log_exists": log_path.exists(),
            "log_path": str(log_path),
            **events,
        })

    return {
        "now": now.isoformat(),
        "cron_in_sync": installed_cron.strip() == template_cron.strip(),
        "jobs": items,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self.send_json(build_status())
            return
        if parsed.path in ("", "/"):
            self.send_file(DASHBOARD_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self.send_file(DASHBOARD_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self.send_file(DASHBOARD_DIR / "styles.css", "text/css; charset=utf-8")
            return
        self.send_error(404)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("", "/", "/app.js", "/styles.css", "/api/status"):
            self.send_response(200)
            content_type = "application/json; charset=utf-8" if parsed.path == "/api/status" else "text/html; charset=utf-8"
            if parsed.path == "/app.js":
                content_type = "application/javascript; charset=utf-8"
            elif parsed.path == "/styles.css":
                content_type = "text/css; charset=utf-8"
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_error(404)

    def send_json(self, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    port = int(os.environ.get("CODEX_AUTOMATIONS_DASHBOARD_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"dashboard listening on http://127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
