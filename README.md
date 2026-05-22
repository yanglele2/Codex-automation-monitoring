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

Local live dashboard:

```bash
python3 /root/codex-automations/dashboard/server.py
```

Then open:

```text
http://127.0.0.1:8765
```

Vercel deployment is supported as a read-only configuration view. It cannot read
the local machine's logs, state markers, or crontab at runtime.

The hosted Vercel panel can display a local status snapshot when
`export-status-snapshot.sh` runs. The default crontab uploads a snapshot every
4 hours by committing `status-snapshot.json` and pushing to GitHub.

## Install Crontab

```bash
crontab /root/codex-automations/crontab.with-catchup
```
