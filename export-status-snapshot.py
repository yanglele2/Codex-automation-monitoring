#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path("/root/codex-automations")
sys.path.insert(0, str(BASE / "dashboard"))

from server import build_status  # noqa: E402


def main() -> None:
    status = build_status()
    status["deployment_mode"] = "snapshot-4h"
    status["snapshot_source"] = "local-cron"
    for job in status.get("jobs", []):
        job["tail"] = job.get("tail", [])[-30:]
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
