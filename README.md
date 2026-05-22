# Codex Automations

Local scheduled Codex automation jobs for financial research workflows.

## Components

- `run.sh` runs one job and validates the result before writing a done marker.
- `run-if-missed.sh` performs catch-up runs inside each configured window.
- `validate-output.sh` checks each run for expected Notion write/readback evidence.
- `prompts/` contains job prompts.
- `dashboard/` serves a local monitoring panel at `http://127.0.0.1:8765`.
- `crontab.with-catchup` is the installable crontab template.

## Dashboard

```bash
python3 /root/codex-automations/dashboard/server.py
```

Then open:

```text
http://127.0.0.1:8765
```

## Install Crontab

```bash
crontab /root/codex-automations/crontab.with-catchup
```
